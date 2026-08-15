from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.content_lifecycle import ContentLifecycleService
from app.services.content_storage import (
    LocalContentStorage,
    content_storage_ref,
    sha256_content_hash,
)
from app.services.resource_authority import (
    ContentReference,
    ContentReferenceIssue,
    InMemoryResourceAuthority,
    PersistentResourceAuthority,
)
from app.schemas.scientific_skills import (
    ModelArtifactContent,
    scientific_artifact_output_hash,
)
from app.commands.content_storage_audit import main as audit_command
from app.config import settings


def _reference(
    content: bytes,
    *,
    resource_id: str,
    project_id: str = "project-a",
    storage_ref: str | None = None,
    size_bytes: int | None = None,
) -> ContentReference:
    content_hash = sha256_content_hash(content)
    return ContentReference(
        project_id=project_id,
        resource_type="research_input_content",
        resource_id=resource_id,
        content_hash=content_hash,
        storage_ref=storage_ref or content_storage_ref(content_hash),
        declared_size_bytes=len(content) if size_bytes is None else size_bytes,
    )


def test_streaming_store_and_inspection_are_content_addressed(tmp_path: Path) -> None:
    storage = LocalContentStorage(tmp_path / "cas")
    chunks = (b"a" * 700_000, b"b" * 700_000, b"c" * 17)
    content = b"".join(chunks)
    content_hash = sha256_content_hash(content)

    async def source():
        for chunk in chunks:
            yield chunk

    ref = asyncio.run(
        storage.store_stream(source(), content_hash, expected_size=len(content))
    )
    inspections = asyncio.run(storage.inspect())

    assert ref == content_storage_ref(content_hash)
    assert len(inspections) == 1
    assert inspections[0].content_hash == content_hash
    assert inspections[0].actual_content_hash == content_hash
    assert inspections[0].size_bytes == len(content)
    assert inspections[0].status == "ok"


@pytest.mark.parametrize("failure", ["hash", "size"])
def test_streaming_store_rejects_incomplete_identity_and_cleans_temp(
    tmp_path: Path, failure: str
) -> None:
    storage = LocalContentStorage(tmp_path / "cas")
    content = b"bounded stream"
    content_hash = sha256_content_hash(content)

    async def source():
        yield content[:4]
        yield content[4:]

    with pytest.raises(ValueError, match="does not match"):
        asyncio.run(
            storage.store_stream(
                source(),
                "sha256:" + "f" * 64 if failure == "hash" else content_hash,
                expected_size=len(content) + (1 if failure == "size" else 0),
            )
        )
    assert list((tmp_path / "cas").rglob(".tmp_*")) == []


def test_lifecycle_report_protects_full_reference_closure_and_lists_orphans(
    tmp_path: Path,
) -> None:
    storage = LocalContentStorage(tmp_path / "cas")
    authority = InMemoryResourceAuthority()
    shared = b"shared referenced bytes"
    derived = b"canonical parse bytes"
    orphan = b"publication lost before database commit"
    for content in (shared, derived, orphan):
        asyncio.run(storage.store(content, sha256_content_hash(content)))

    authority.register_content_reference(
        _reference(shared, resource_id="input-a", project_id="project-a")
    )
    authority.register_content_reference(
        _reference(shared, resource_id="model-a", project_id="project-b")
    )
    authority.register_content_reference(
        _reference(derived, resource_id="parse-a", project_id="project-a")
    )

    report = asyncio.run(
        ContentLifecycleService(storage=storage, authority=authority).inspect()
    )

    assert report.integrity_ok is True
    assert report.reference_count == 3
    assert report.referenced_hash_count == 2
    assert report.orphan_blob_count == 1
    assert report.orphan_bytes == len(orphan)
    assert report.orphans[0].content_hash == sha256_content_hash(orphan)
    assert report.deletion_supported is False


def test_lifecycle_report_fails_closed_on_corruption_missing_refs_and_authority_gaps(
    tmp_path: Path,
) -> None:
    storage = LocalContentStorage(tmp_path / "cas")
    authority = InMemoryResourceAuthority()
    corrupt = b"corrupt target"
    missing = b"missing target"
    wrong_size = b"size target"
    for content in (corrupt, wrong_size):
        asyncio.run(storage.store(content, sha256_content_hash(content)))

    corrupt_path = (
        tmp_path / "cas" / content_storage_ref(sha256_content_hash(corrupt))
    )
    corrupt_path.write_bytes(b"tampered")
    (tmp_path / "cas" / "unexpected.zip").write_bytes(b"not an input")

    authority.register_content_reference(
        _reference(corrupt, resource_id="corrupt-version")
    )
    authority.register_content_reference(
        _reference(missing, resource_id="missing-input")
    )
    authority.register_content_reference(
        _reference(wrong_size, resource_id="bad-size", size_bytes=999)
    )
    authority.register_content_reference(
        _reference(
            wrong_size,
            resource_id="bad-ref",
            storage_ref="outside/the-canonical-store",
        )
    )
    authority.register_content_reference_issue(
        ContentReferenceIssue(
            project_id="project-a",
            resource_type="artifact_version",
            resource_id="malformed-model-version",
            reason="model binary reference is not schema-valid",
        )
    )

    report = asyncio.run(
        ContentLifecycleService(storage=storage, authority=authority).inspect()
    )
    codes = {finding.code for finding in report.findings}

    assert report.integrity_ok is False
    assert {
        "authority_uncertain",
        "blob_hash_mismatch",
        "blob_missing",
        "blob_size_mismatch",
        "reference_ref_mismatch",
        "unexpected_storage_entry",
    } <= codes
    assert report.orphan_blob_count == 0


def test_content_lifecycle_has_no_public_or_destructive_surface() -> None:
    report_type_fields = ContentLifecycleService.inspect.__annotations__

    assert "return" in report_type_fields
    assert not hasattr(ContentLifecycleService, "delete")
    assert not hasattr(LocalContentStorage, "delete")


def test_operator_command_fails_closed_without_database_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(settings, "DATABASE_URL", None)

    assert audit_command() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "CONTENT_STORAGE_AUDIT_FAILED" in captured.err
    assert "Traceback" not in captured.err


def test_persistent_authority_closes_direct_and_model_artifact_blob_refs() -> None:
    project_id = uuid4()
    parse_id = uuid4()
    version_id = uuid4()
    input_content = b"input"
    parse_content = b"parse"
    model_content = b"onnx"
    input_hash = sha256_content_hash(input_content)
    parse_hash = sha256_content_hash(parse_content)
    model_hash = sha256_content_hash(model_content)

    class FakeResult(tuple):
        def yield_per(self, _size: int):
            return self

    class FakeSession:
        def __init__(self) -> None:
            self.results = iter(
                (
                    (
                        (
                            project_id,
                            input_hash,
                            content_storage_ref(input_hash),
                            len(input_content),
                        ),
                    ),
                    (
                        (
                            parse_id,
                            project_id,
                            parse_hash,
                            content_storage_ref(parse_hash),
                        ),
                    ),
                    (
                        (
                            version_id,
                            project_id,
                            "model_artifact",
                            _model_artifact_payload(model_hash),
                        ),
                    ),
                )
            )

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def execute(self, _statement):
            return FakeResult(next(self.results))

    session = FakeSession()
    closure = PersistentResourceAuthority(lambda: session).content_reference_closure()

    assert closure.issues == ()
    assert {item.resource_type for item in closure.references} == {
        "research_input_content",
        "document_parse_payload",
        "artifact_version_binary",
    }
    assert {item.content_hash for item in closure.references} == {
        input_hash,
        parse_hash,
        model_hash,
    }


def _model_artifact_payload(content_hash: str) -> dict[str, object]:
    hash_a = "sha256:" + "a" * 64
    hash_b = "sha256:" + "b" * 64
    payload: dict[str, object] = {
        "kind": "model_artifact",
        "schema_version": "1.0.0",
        "model_id": "model.classifier",
        "title": "Host-star classifier model",
        "status": "active",
        "task_kind": "classification",
        "algorithm": "random_forest",
        "algorithm_version": "scikit-learn:current",
        "training_input": {
            "kind": "dataset_artifact_version",
            "ref_id": "version.dataset",
        },
        "evaluation_id": "evaluation.classifier",
        "feature_fields": ["star.mass", "star.radius"],
        "target_field": "star.class",
        "model_binary": {
            "content_ref": content_storage_ref(content_hash),
            "content_hash": content_hash,
            "media_type": "application/onnx",
        },
        "input_name": "X",
        "output_names": ["label", "probabilities"],
        "input_shape": [None, 2],
        "opset_imports": {"ai.onnx": 21, "ai.onnx.ml": 3},
        "dependency_revisions": [
            "onnx==1.22.0",
            "onnxruntime==1.28.0",
            "scikit-learn==1.9.1",
            "skl2onnx==1.20.0",
        ],
        "skill_execution": {
            "execution_id": "skill.training",
            "skill_id": "tabular_machine_learning",
            "skill_revision": "1.0.0",
            "status": "completed",
            "input_hash": hash_a,
            "output_hash": hash_b,
            "duration_ms": 12,
            "warnings": [],
        },
        "limitations": [],
        "source_snapshot_ids": [],
        "evidence_ids": [],
        "input_hash": hash_a,
    }
    sealed = deepcopy(payload)
    sealed["output_hash"] = scientific_artifact_output_hash(sealed)
    return ModelArtifactContent.model_validate(sealed).model_dump(mode="json")
