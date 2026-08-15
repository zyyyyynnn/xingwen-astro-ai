from __future__ import annotations

from io import BytesIO
import json
from stat import S_IFLNK
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest
from PIL import Image

from app.services.image_dataset import (
    ImageDatasetPolicy,
    resolve_image_dataset_archive,
)


def _png_bytes(*, color: tuple[int, int, int], size: tuple[int, int] = (12, 8)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color=color).save(output, format="PNG")
    return output.getvalue()


def _archive(
    entries: list[dict[str, str]],
    *,
    extra_members: dict[str, bytes] | None = None,
    symlink: str | None = None,
) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "labels.json",
            json.dumps(
                {"schema_version": "1.0.0", "images": entries},
                ensure_ascii=False,
            ).encode("utf-8"),
        )
        for index, entry in enumerate(entries):
            archive.writestr(
                entry["path"],
                _png_bytes(color=(index * 10 % 255, 20, 30)),
            )
        for name, content in (extra_members or {}).items():
            archive.writestr(name, content)
        if symlink is not None:
            info = ZipInfo(symlink)
            info.create_system = 3
            info.external_attr = (S_IFLNK | 0o777) << 16
            archive.writestr(info, b"target.png")
    return output.getvalue()


def _entries() -> list[dict[str, str]]:
    return [
        {
            "path": f"images/sample-{index:02d}.png",
            "label": "galaxy" if index < 5 else "star",
        }
        for index in range(10)
    ]


def _mark_first_member_encrypted(content: bytes) -> bytes:
    mutated = bytearray(content)
    local = mutated.find(b"PK\x03\x04")
    central = mutated.find(b"PK\x01\x02")
    assert local >= 0 and central >= 0
    local_flags = int.from_bytes(mutated[local + 6 : local + 8], "little") | 0x1
    central_flags = int.from_bytes(mutated[central + 8 : central + 10], "little") | 0x1
    mutated[local + 6 : local + 8] = local_flags.to_bytes(2, "little")
    mutated[central + 8 : central + 10] = central_flags.to_bytes(2, "little")
    return bytes(mutated)


def test_image_dataset_resolves_to_fixed_rgb_training_parameters() -> None:
    parameters = resolve_image_dataset_archive(
        _archive(_entries()), policy=ImageDatasetPolicy()
    )

    assert parameters["image_shape"] == [32, 32, 3]
    assert parameters["preprocessing"] == {
        "schema_version": "1.0.0",
        "color_mode": "RGB",
        "exif_transpose": True,
        "resize_height": 32,
        "resize_width": 32,
        "resize_mode": "contain_pad",
        "resampling": "bilinear",
        "normalization": "uint8_to_unit_interval",
    }
    assert parameters["label_schema"] == [
        {"class_index": 0, "label": "galaxy", "sample_count": 5},
        {"class_index": 1, "label": "star", "sample_count": 5},
    ]
    images = parameters["images"]
    assert isinstance(images, list) and len(images) == 10
    assert images[0]["image_id"] == "images/sample-00.png"
    assert len(images[0]["pixels"]) == 32 * 32 * 3
    assert all(0 <= value <= 1 for value in images[0]["pixels"])


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda entries: entries
            + [{"path": "../outside.png", "label": "star"}],
            "relative POSIX",
        ),
        (
            lambda entries: entries[:-1]
            + [{"path": "IMAGES/SAMPLE-00.PNG", "label": "star"}],
            "case-insensitive",
        ),
        (
            lambda entries: entries[:-1]
            + [{"path": "images/only-one.png", "label": "quasar"}],
            "at least 2 samples",
        ),
    ],
)
def test_image_dataset_rejects_unsafe_paths_and_underrepresented_classes(
    mutate, message: str  # noqa: ANN001
) -> None:
    with pytest.raises(ValueError, match=message):
        resolve_image_dataset_archive(
            _archive(mutate(_entries())), policy=ImageDatasetPolicy()
        )


def test_image_dataset_rejects_members_outside_manifest_and_symlinks() -> None:
    with pytest.raises(ValueError, match="allowlist"):
        resolve_image_dataset_archive(
            _archive(_entries(), extra_members={"unlisted.png": _png_bytes(color=(0, 0, 0))}),
            policy=ImageDatasetPolicy(),
        )
    entries = _entries()
    entries[-1] = {"path": "images/link.png", "label": "star"}
    with pytest.raises(ValueError, match="symbolic link"):
        resolve_image_dataset_archive(
            _archive(entries[:-1], symlink="images/link.png"),
            policy=ImageDatasetPolicy(),
        )


def test_image_dataset_rejects_encrypted_members() -> None:
    with pytest.raises(ValueError, match="encrypted"):
        resolve_image_dataset_archive(
            _mark_first_member_encrypted(_archive(_entries())),
            policy=ImageDatasetPolicy(),
        )


def test_image_dataset_enforces_compression_and_pixel_budgets() -> None:
    with pytest.raises(ValueError, match="compression ratio"):
        resolve_image_dataset_archive(
            _archive(
                _entries(),
                extra_members={"padding.bin": b"A" * 10_000},
            ),
            policy=ImageDatasetPolicy(max_compression_ratio=2),
        )
    with pytest.raises(ValueError, match="dimensions"):
        entries = _entries()
        content = _archive(entries)
        resolve_image_dataset_archive(
            content,
            policy=ImageDatasetPolicy(max_image_dimension=4),
        )


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        (ImageDatasetPolicy(max_archive_members=11), "member budget"),
        (ImageDatasetPolicy(max_uncompressed_bytes=100), "uncompressed byte"),
        (ImageDatasetPolicy(max_image_bytes=10), "single-image byte"),
        (ImageDatasetPolicy(max_total_pixels=100), "total pixel"),
    ],
)
def test_image_dataset_enforces_each_archive_resource_budget(
    policy: ImageDatasetPolicy, message: str
) -> None:
    content = _archive(
        _entries(),
        extra_members=(
            {"extra.txt": b"not admitted"} if message == "member budget" else None
        ),
    )
    with pytest.raises(ValueError, match=message):
        resolve_image_dataset_archive(content, policy=policy)
