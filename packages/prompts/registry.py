"""Immutable loader for production prompts registered in this package."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


CONTENT_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
VERSION_PATTERN = re.compile(r"^v[1-9][0-9]*$")


class PromptRegistryError(ValueError):
    """The registry or one immutable prompt version is invalid."""


@dataclass(frozen=True, slots=True)
class PromptRecord:
    name: str
    version: str
    path: str
    content_hash: str
    output_models: tuple[str, ...]
    status: str
    content: str
    front_matter: dict[str, str]


class PromptRegistry:
    """Resolve prompts only through hash-pinned version records."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parent
        self._current, self._records = self._load()

    def get(self, name: str, version: str | None = None) -> PromptRecord:
        selected = version or self._current.get(name)
        if selected is None:
            raise KeyError(f"unknown prompt: {name}")
        try:
            return self._records[(name, selected)]
        except KeyError as exc:
            raise KeyError(f"unknown prompt version: {name}@{selected}") from exc

    def versions(self, name: str) -> tuple[PromptRecord, ...]:
        records = tuple(
            record
            for (record_name, _), record in self._records.items()
            if record_name == name
        )
        if not records:
            raise KeyError(f"unknown prompt: {name}")
        return tuple(sorted(records, key=lambda record: record.version))

    def _load(self) -> tuple[dict[str, str], dict[tuple[str, str], PromptRecord]]:
        registry_path = self.root / "registry.json"
        try:
            payload = json.loads(
                registry_path.read_text(encoding="utf-8"),
                object_pairs_hook=_unique_object,
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise PromptRegistryError("prompt registry cannot be loaded") from exc
        if payload.get("registry_version") != 2 or set(payload) != {
            "registry_version",
            "prompts",
        }:
            raise PromptRegistryError("unsupported prompt registry structure")
        prompts = payload.get("prompts")
        if not isinstance(prompts, dict) or not prompts:
            raise PromptRegistryError("prompt registry must contain prompts")

        current: dict[str, str] = {}
        records: dict[tuple[str, str], PromptRecord] = {}
        paths: set[str] = set()
        hashes: set[str] = set()
        for name, prompt in prompts.items():
            if not isinstance(name, str) or not name or not isinstance(prompt, dict):
                raise PromptRegistryError("invalid prompt registry entry")
            if set(prompt) != {"current", "versions"}:
                raise PromptRegistryError(f"invalid registry fields for {name}")
            selected = prompt.get("current")
            versions = prompt.get("versions")
            if not isinstance(selected, str) or not isinstance(versions, dict):
                raise PromptRegistryError(f"invalid versions for {name}")
            if selected not in versions:
                raise PromptRegistryError(f"current version is not registered for {name}")
            current[name] = selected
            for version, raw_record in versions.items():
                record = self._load_record(name, version, raw_record)
                key = (name, version)
                if key in records or record.path in paths or record.content_hash in hashes:
                    raise PromptRegistryError("prompt versions, paths, and hashes must be unique")
                records[key] = record
                paths.add(record.path)
                hashes.add(record.content_hash)
        return current, records

    def _load_record(self, name: str, version: str, raw_record: Any) -> PromptRecord:
        if not VERSION_PATTERN.fullmatch(version) or not isinstance(raw_record, dict):
            raise PromptRegistryError(f"invalid prompt version for {name}")
        required = {"path", "content_hash", "output_models", "status"}
        if set(raw_record) != required:
            raise PromptRegistryError(f"invalid version record for {name}@{version}")
        path = raw_record["path"]
        content_hash = raw_record["content_hash"]
        output_models = raw_record["output_models"]
        status = raw_record["status"]
        if (
            not isinstance(path, str)
            or Path(path).is_absolute()
            or ".." in Path(path).parts
            or not isinstance(content_hash, str)
            or not CONTENT_HASH_PATTERN.fullmatch(content_hash)
            or not isinstance(output_models, list)
            or not output_models
            or not all(isinstance(item, str) and item for item in output_models)
            or status not in {"active", "deprecated", "disabled"}
        ):
            raise PromptRegistryError(f"invalid metadata for {name}@{version}")
        prompt_path = self.root / path
        try:
            content = prompt_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PromptRegistryError(f"prompt file is missing for {name}@{version}") from exc
        actual_hash = compute_prompt_content_hash(content)
        if actual_hash != content_hash:
            raise PromptRegistryError(f"immutable prompt content changed for {name}@{version}")
        front_matter = _parse_front_matter(content)
        if front_matter.get("name") != name or front_matter.get("version") != version:
            raise PromptRegistryError(f"front matter mismatch for {name}@{version}")
        declared_outputs = tuple(
            item.strip()
            for item in front_matter.get(
                "output_models", front_matter.get("output_model", "")
            ).split(",")
            if item.strip()
        )
        if declared_outputs != tuple(output_models):
            raise PromptRegistryError(f"output model mismatch for {name}@{version}")
        return PromptRecord(
            name=name,
            version=version,
            path=path,
            content_hash=content_hash,
            output_models=tuple(output_models),
            status=status,
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
