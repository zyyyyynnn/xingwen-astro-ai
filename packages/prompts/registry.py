"""Immutable loader for production prompts registered in this package."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


CONTENT_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
VERSION_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


class PromptRegistryError(ValueError):
    """The registry or one hash-pinned prompt definition is invalid."""


@dataclass(frozen=True, slots=True)
class PromptRecord:
    name: str
    version: str
    path: str
    content_hash: str
    output_models: tuple[str, ...]
    input_schema_version: str
    output_schema_version: str
    evidence_required: bool
    content: str
    front_matter: dict[str, str]


class PromptRegistry:
    """Resolve each production prompt through one hash-pinned current record."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parent
        self._records = self._load()

    def get(self, name: str) -> PromptRecord:
        try:
            return self._records[name]
        except KeyError as exc:
            raise KeyError(f"unknown prompt: {name}") from exc

    def _load(self) -> dict[str, PromptRecord]:
        registry_path = self.root / "registry.json"
        try:
            payload = json.loads(
                registry_path.read_text(encoding="utf-8"),
                object_pairs_hook=_unique_object,
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise PromptRegistryError("prompt registry cannot be loaded") from exc
        if payload.get("schema_version") != "1.0.0" or set(payload) != {
            "schema_version",
            "prompts",
        }:
            raise PromptRegistryError("unsupported prompt registry structure")
        prompts = payload.get("prompts")
        if not isinstance(prompts, dict) or not prompts:
            raise PromptRegistryError("prompt registry must contain prompts")

        records: dict[str, PromptRecord] = {}
        paths: set[str] = set()
        hashes: set[str] = set()
        for name, raw_record in prompts.items():
            if not isinstance(name, str) or not name:
                raise PromptRegistryError("invalid prompt registry entry")
            record = self._load_record(name, raw_record)
            if record.path in paths or record.content_hash in hashes:
                raise PromptRegistryError("prompt paths and hashes must be unique")
            records[name] = record
            paths.add(record.path)
            hashes.add(record.content_hash)
        return records

    def _load_record(self, name: str, raw_record: Any) -> PromptRecord:
        if not isinstance(raw_record, dict):
            raise PromptRegistryError(f"invalid prompt record for {name}")
        required = {"version", "path", "content_hash", "output_models"}
        if set(raw_record) != required:
            raise PromptRegistryError(f"invalid prompt record for {name}")
        version = raw_record["version"]
        path = raw_record["path"]
        content_hash = raw_record["content_hash"]
        output_models = raw_record["output_models"]
        if (
            not isinstance(version, str)
            or not VERSION_PATTERN.fullmatch(version)
            or not isinstance(path, str)
            or Path(path).is_absolute()
            or ".." in Path(path).parts
            or not isinstance(content_hash, str)
            or not CONTENT_HASH_PATTERN.fullmatch(content_hash)
            or not isinstance(output_models, list)
            or not output_models
            or not all(isinstance(item, str) and item for item in output_models)
        ):
            raise PromptRegistryError(f"invalid metadata for {name}")
        prompt_path = self.root / path
        try:
            content = prompt_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PromptRegistryError(f"prompt file is missing for {name}") from exc
        actual_hash = compute_prompt_content_hash(content)
        if actual_hash != content_hash:
            raise PromptRegistryError(f"immutable prompt content changed for {name}")
        front_matter = _parse_front_matter(content)
        output_key = (
            "output_models" if "output_models" in front_matter else "output_model"
        )
        required_front_matter = {
            "name",
            "version",
            output_key,
            "input_schema_version",
            "output_schema_version",
            "evidence_required",
        }
        if set(front_matter) != required_front_matter:
            raise PromptRegistryError(f"invalid front matter fields for {name}")
        if front_matter.get("name") != name or front_matter.get("version") != version:
            raise PromptRegistryError(f"front matter mismatch for {name}")
        declared_outputs = tuple(
            item.strip()
            for item in front_matter.get(
                "output_models", front_matter.get("output_model", "")
            ).split(",")
            if item.strip()
        )
        if declared_outputs != tuple(output_models):
            raise PromptRegistryError(f"output model mismatch for {name}")
        input_schema_version = front_matter["input_schema_version"]
        output_schema_version = front_matter["output_schema_version"]
        evidence_required = front_matter["evidence_required"]
        if (
            not VERSION_PATTERN.fullmatch(input_schema_version)
            or not VERSION_PATTERN.fullmatch(output_schema_version)
            or evidence_required not in {"true", "false"}
        ):
            raise PromptRegistryError(f"invalid prompt contract metadata for {name}")
        return PromptRecord(
            name=name,
            version=version,
            path=path,
            content_hash=content_hash,
            output_models=tuple(output_models),
            input_schema_version=input_schema_version,
            output_schema_version=output_schema_version,
            evidence_required=evidence_required == "true",
            content=content,
            front_matter=front_matter,
        )


def compute_prompt_content_hash(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    return f"sha256:{sha256(normalized.encode('utf-8')).hexdigest()}"


def _parse_front_matter(content: str) -> dict[str, str]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines()
    if not lines or lines[0] != "---":
        raise PromptRegistryError("prompt front matter is missing")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise PromptRegistryError("prompt front matter is not terminated") from exc
    result: dict[str, str] = {}
    current_list_key: str | None = None
    list_values: list[str] = []
    for line in lines[1:end]:
        if not line.strip():
            continue
        if line.startswith("  - ") and current_list_key is not None:
            item = line[4:].strip()
            if not item:
                raise PromptRegistryError("prompt front matter list is invalid")
            list_values.append(item)
            result[current_list_key] = ",".join(list_values)
            continue
        key, separator, value = line.partition(":")
        normalized_key = key.strip()
        if not separator or not normalized_key or normalized_key in result:
            raise PromptRegistryError("prompt front matter is invalid")
        if value.strip():
            result[normalized_key] = value.strip()
            current_list_key = None
            list_values = []
        else:
            result[normalized_key] = ""
            current_list_key = normalized_key
            list_values = []
    return result


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PromptRegistryError(f"duplicate registry key: {key}")
        result[key] = value
    return result
