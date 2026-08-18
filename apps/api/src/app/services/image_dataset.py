"""Bounded ZIP + label-manifest boundary for image-classification inputs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import PurePosixPath
import stat
import unicodedata
from typing import Annotated, Any, Literal
from zipfile import (
    BadZipFile,
    ZIP_DEFLATED,
    ZIP_STORED,
    ZipFile,
    ZipInfo,
)

from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError


_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
_LABELS_MEMBER = "labels.json"
_MAX_MANIFEST_BYTES = 256 * 1024
_IMAGE_FORMATS = {
    ".jpeg": "JPEG",
    ".jpg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
_PREPROCESSING = {
    "schema_version": "1.0.0",
    "color_mode": "RGB",
    "exif_transpose": True,
    "resize_height": 32,
    "resize_width": 32,
    "resize_mode": "contain_pad",
    "resampling": "bilinear",
    "normalization": "uint8_to_unit_interval",
}


@dataclass(frozen=True, slots=True)
class ImageDatasetPolicy:
    """Resource limits applied before any archive member is decoded."""

    max_archive_members: int = 512
    max_uncompressed_bytes: int = 64 * 1024 * 1024
    max_compression_ratio: int = 100
    max_image_bytes: int = 8 * 1024 * 1024
    max_image_dimension: int = 4096
    max_total_pixels: int = 16_000_000
    max_images: int = 256
    max_classes: int = 32
    min_samples_per_class: int = 2

    def __post_init__(self) -> None:
        values = (
            self.max_archive_members,
            self.max_uncompressed_bytes,
            self.max_compression_ratio,
            self.max_image_bytes,
            self.max_image_dimension,
            self.max_total_pixels,
            self.max_images,
            self.max_classes,
            self.min_samples_per_class,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("image dataset limits must be positive integers")
        if self.max_archive_members < 11 or self.max_images < 10:
            raise ValueError("image dataset policy must admit at least 10 images")
        if self.max_classes < 2:
            raise ValueError("image dataset policy must admit at least two classes")


_ManifestPath = Annotated[
    str,
    StringConstraints(strip_whitespace=False, min_length=1, max_length=255),
]
_ManifestLabel = Annotated[
    str,
    StringConstraints(strip_whitespace=False, min_length=1, max_length=64),
]


class _ManifestImage(BaseModel):
    model_config = _MODEL_CONFIG

    path: _ManifestPath
    label: _ManifestLabel


class _LabelManifest(BaseModel):
    model_config = _MODEL_CONFIG

    schema_version: Literal["1.0.0"]
    images: tuple[_ManifestImage, ...] = Field(min_length=10)


def resolve_image_dataset_archive(
    content: bytes,
    *,
    policy: ImageDatasetPolicy,
) -> dict[str, object]:
    """Validate one archive and return deterministic, preprocessed parameters.

    Archive members are read through :mod:`zipfile` and Pillow decodes images;
    no member is ever extracted to a filesystem path.
    """

    try:
        with ZipFile(BytesIO(content)) as archive:
            members, directories = _validated_members(archive, policy=policy)
            manifest_member = members.get(_LABELS_MEMBER)
            if manifest_member is None:
                raise ValueError("image dataset requires root labels.json")
            manifest = _read_manifest(archive, manifest_member)
            if len(manifest.images) > policy.max_images:
                raise ValueError("image dataset exceeds the image count budget")
            paths = _validated_manifest_paths(manifest)
            expected_directories = _manifest_directories(paths)
            if set(members) != {_LABELS_MEMBER, *paths} or not directories.issubset(
                expected_directories
            ):
                raise ValueError("image dataset archive members violate the manifest allowlist")
            labels = tuple(item.label for item in manifest.images)
            label_schema = _label_schema(labels, policy=policy)
            images, total_pixels = _decode_images(
                archive,
                manifest=manifest,
                members=members,
                policy=policy,
            )
    except ValueError:
        raise
    except (BadZipFile, OSError) as exc:
        raise ValueError("image dataset ZIP is malformed") from exc
    return {
        "images": images,
        "image_count": len(images),
        "source_total_pixels": total_pixels,
        "image_shape": [32, 32, 3],
        "preprocessing": dict(_PREPROCESSING),
        "label_schema": label_schema,
    }


def validate_image_dataset_archive(
    content: bytes,
    *,
    policy: ImageDatasetPolicy,
) -> None:
    """Admission gate used before an image-dataset upload is committed."""

    resolve_image_dataset_archive(content, policy=policy)


def _validated_members(
    archive: ZipFile,
    *,
    policy: ImageDatasetPolicy,
) -> tuple[dict[str, ZipInfo], set[str]]:
    infos = archive.infolist()
    if not infos or len(infos) > policy.max_archive_members:
        raise ValueError("image dataset exceeds the archive member budget")
    members: dict[str, ZipInfo] = {}
    directories: set[str] = set()
    casefolded: set[str] = set()
    total_uncompressed = 0
    total_compressed = 0
    for info in infos:
        name = _validated_posix_path(info.filename, directory=info.is_dir())
        folded = name.casefold()
        if folded in casefolded:
            raise ValueError("image dataset member paths collide case-insensitively")
        casefolded.add(folded)
        if info.flag_bits & 0x1:
            raise ValueError("image dataset cannot contain encrypted members")
        mode = info.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if kind == stat.S_IFLNK:
            raise ValueError("image dataset cannot contain a symbolic link")
        if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise ValueError("image dataset cannot contain a special file")
        if info.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
            raise ValueError("image dataset uses an unsupported ZIP compression method")
        if info.is_dir():
            if info.file_size != 0:
                raise ValueError("image dataset directory entries must be empty")
            directories.add(name)
            continue
        total_uncompressed += info.file_size
        total_compressed += info.compress_size
        if total_uncompressed > policy.max_uncompressed_bytes:
            raise ValueError("image dataset exceeds the uncompressed byte budget")
        if info.file_size > max(info.compress_size, 1) * policy.max_compression_ratio:
            raise ValueError("image dataset member exceeds the compression ratio budget")
        members[name] = info
    if total_uncompressed > max(total_compressed, 1) * policy.max_compression_ratio:
        raise ValueError("image dataset exceeds the total compression ratio budget")
    return members, directories


def _validated_posix_path(raw: str, *, directory: bool = False) -> str:
    candidate = raw[:-1] if directory and raw.endswith("/") else raw
    if (
        not candidate
        or raw != unicodedata.normalize("NFC", raw)
        or "\\" in raw
        or raw.startswith("/")
        or ":" in raw
        or any(ord(character) < 32 or ord(character) == 127 for character in raw)
    ):
        raise ValueError("image dataset member path must be a relative POSIX path")
    parts = candidate.split("/")
    path = PurePosixPath(candidate)
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in parts)
        or len(candidate) > 255
        or any(len(part) > 128 for part in parts)
    ):
        raise ValueError("image dataset member path must be a relative POSIX path")
    return candidate


def _read_manifest(archive: ZipFile, member: ZipInfo) -> _LabelManifest:
    if member.file_size <= 0 or member.file_size > _MAX_MANIFEST_BYTES:
        raise ValueError("image dataset labels.json exceeds its byte budget")
    raw = _read_member(archive, member)
    try:
        text = raw.decode("utf-8")
        payload = json.loads(text, object_pairs_hook=_unique_json_object)
        return _LabelManifest.model_validate(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("image dataset labels.json violates schema_version 1.0.0") from exc


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("image dataset labels.json contains duplicate keys")
        result[key] = value
    return result


def _validated_manifest_paths(manifest: _LabelManifest) -> tuple[str, ...]:
    paths: list[str] = []
    folded: set[str] = set()
    for item in manifest.images:
        path = _validated_posix_path(item.path)
        if path == _LABELS_MEMBER or PurePosixPath(path).suffix.lower() not in _IMAGE_FORMATS:
            raise ValueError("image dataset manifest path is not an allowed image member")
        if path.casefold() in folded:
            raise ValueError("image dataset manifest paths collide case-insensitively")
        folded.add(path.casefold())
        paths.append(path)
    return tuple(paths)


def _manifest_directories(paths: tuple[str, ...]) -> set[str]:
    result: set[str] = set()
    for raw in paths:
        parents = PurePosixPath(raw).parents
        result.update(str(parent) for parent in parents if str(parent) != ".")
    return result


def _label_schema(
    labels: tuple[str, ...],
    *,
    policy: ImageDatasetPolicy,
) -> list[dict[str, object]]:
    normalized = tuple(unicodedata.normalize("NFC", label.strip()) for label in labels)
    if any(label != original for label, original in zip(normalized, labels, strict=True)):
        raise ValueError("image dataset labels must use trimmed NFC text")
    counts = Counter(normalized)
    if len(counts) < 2 or len(counts) > policy.max_classes:
        raise ValueError("image dataset label count is outside the class budget")
    folded = [label.casefold() for label in counts]
    if len(folded) != len(set(folded)):
        raise ValueError("image dataset labels collide case-insensitively")
    if min(counts.values()) < policy.min_samples_per_class:
        raise ValueError(
            f"image dataset requires at least {policy.min_samples_per_class} samples per class"
        )
    return [
        {"class_index": index, "label": label, "sample_count": counts[label]}
        for index, label in enumerate(sorted(counts, key=lambda value: (value.casefold(), value)))
    ]


def _decode_images(
    archive: ZipFile,
    *,
    manifest: _LabelManifest,
    members: dict[str, ZipInfo],
    policy: ImageDatasetPolicy,
) -> tuple[list[dict[str, object]], int]:
    images: list[dict[str, object]] = []
    total_pixels = 0
    for item in manifest.images:
        member = members[item.path]
        if member.file_size <= 0 or member.file_size > policy.max_image_bytes:
            raise ValueError("image dataset member exceeds the single-image byte budget")
        raw = _read_member(archive, member)
        try:
            with Image.open(BytesIO(raw)) as source:
                expected_format = _IMAGE_FORMATS[PurePosixPath(item.path).suffix.lower()]
                if source.format != expected_format or getattr(source, "n_frames", 1) != 1:
                    raise ValueError("image dataset member format does not match its path")
                width, height = source.size
                if (
                    width <= 0
                    or height <= 0
                    or width > policy.max_image_dimension
                    or height > policy.max_image_dimension
                ):
                    raise ValueError("image dataset member dimensions exceed the budget")
                total_pixels += width * height
                if total_pixels > policy.max_total_pixels:
                    raise ValueError("image dataset exceeds the total pixel budget")
                source.load()
                transposed = ImageOps.exif_transpose(source)
                rgb = transposed.convert("RGB")
                normalized = ImageOps.pad(
                    rgb,
                    (32, 32),
                    method=Image.Resampling.BILINEAR,
                    color=(0, 0, 0),
                    centering=(0.5, 0.5),
                )
                pixels = [channel / 255.0 for channel in normalized.tobytes()]
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001 - Pillow exception types vary by codec
            raise ValueError("image dataset contains an invalid image member") from exc
        images.append(
            {
                "image_id": item.path,
                "label": item.label,
                "pixels": pixels,
            }
        )
    return images, total_pixels


def _read_member(archive: ZipFile, member: ZipInfo) -> bytes:
    try:
        with archive.open(member, "r") as stream:
            content = stream.read(member.file_size + 1)
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise ValueError("image dataset ZIP member cannot be decoded") from exc
    if len(content) != member.file_size:
        raise ValueError("image dataset ZIP member size is inconsistent")
    return content


__all__ = [
    "ImageDatasetPolicy",
    "resolve_image_dataset_archive",
    "validate_image_dataset_archive",
]
