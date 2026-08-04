from __future__ import annotations

from datetime import UTC, datetime
import pytest

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ArtifactKind,
    ArtifactVersionDetail,
    EvidenceDetail,
    ProducerExecutionDetail,
    ProducerReference,
    ResearchArtifact,
    SourceSnapshotDetail,
)
from app.services.data_artifacts import DataArtifactReadService, _csv_cell
from app.security import SecurityProblem

from data_artifact_test_support import build_input
from services.data_pipeline.data_artifacts import build_data_artifact_candidates


def _service_for_dataset() -> tuple[DataArtifactReadService, str]:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).dataset
    content = candidate.model_dump(mode="json")
    version_id = "version-1"
    snapshots = tuple(
        SourceSnapshotDetail.model_construct(
            id=f"snapshot-{index}",
            source_id=f"source-{index}",
            source_type="fixture",
            retrieved_at=datetime.now(UTC),
            query={},
            query_hash="sha256:" + "1" * 64,
            content_hash="sha256:" + "2" * 64,
            license_note="fixture",
            request_metadata={},
        )
        for index, _ in enumerate(candidate.source_snapshot_ids)
    )
    evidence = tuple(
        EvidenceDetail.model_construct(
            id=f"evidence-{index}",
            artifact_version_id=version_id,
            target_type="dataset",
            target_id="target",
            evidence_type="source",
            source_snapshot_id=snapshots[0].id,
            locator={},
            extraction_method="fixture",
            confidence=1.0,
            created_at=datetime.now(UTC),
        )
        for index, _ in enumerate(candidate.evidence_ids)
    )
    producer = ProducerExecutionDetail.model_construct(
        id="producer-1",
        run_id="run-1",
        step_key="data",
        step_attempt_id="attempt-1",
        producer=ProducerReference(type="pipeline", name="data", version="1.0.0"),
        parameters={},
        parameters_hash="sha256:" + "3" * 64,
        input_hash=candidate.input_hash,
        status="completed",
        started_at=datetime.now(UTC),
    )
    version = ArtifactVersionDetail.model_construct(
        id=version_id,
        artifact_id="artifact-1",
        project_id="project-1",
        created_by_run_id="run-1",
        version_number=1,
        schema_version=candidate.schema_version,
        content=content,
        content_hash=compute_canonical_payload_hash(content),
        input_hash=candidate.input_hash,
        source_mode="fixture",
        producer=ProducerReference(type="pipeline", name="data", version="1.0.0"),
        source_snapshot_ids=tuple(item.id for item in snapshots),
        evidence_ids=tuple(item.id for item in evidence),
        supersedes_version_id=None,
        created_at=datetime.now(UTC),
        producer_execution=producer,
        source_snapshots=snapshots,
        evidence=evidence,
    )
    artifact = ResearchArtifact.model_construct(
        id="artifact-1",
        project_id="project-1",
        kind=ArtifactKind.dataset,
        title="Dataset",
        logical_key="dataset.primary",
        created_at=version.created_at,
        latest_version_id=version_id,
    )

    class FakeArtifacts:
        def get_version(self, *, version_id: str, session_id: str, full_content: bool = False):
            assert version_id == version_id_value
            assert session_id == "session-1"
            return version

        def get_artifact(self, *, artifact_id: str, session_id: str):
            return artifact

    version_id_value = version_id
    return DataArtifactReadService(FakeArtifacts()), version_id


def test_dataset_rows_cursor_is_bound_to_version() -> None:
    service, version_id = _service_for_dataset()
    rows, cursor, has_more = service.list_dataset_rows(
        version_id=version_id, session_id="session-1", cursor=None, limit=1
    )
    assert rows
    assert not has_more or cursor
    with pytest.raises(Exception) as exc_info:
        service.list_dataset_rows(
            version_id=version_id,
            session_id="session-1",
            cursor="not-a-valid-cursor",
            limit=1,
        )
    assert getattr(exc_info.value, "code", None) == "INVALID_CURSOR"


def test_dataset_export_is_idempotent_and_rejects_unknown_format() -> None:
    service, version_id = _service_for_dataset()
    first = service.create_export(
        version_id=version_id,
        session_id="session-1",
        idempotency_key="export-1",
        export_format="json",
    )
    replay = service.create_export(
        version_id=version_id,
        session_id="session-1",
        idempotency_key="export-1",
        export_format="json",
    )
    assert replay.export.id == first.export.id
    with pytest.raises(SecurityProblem) as conflict:
        service.create_export(
            version_id=version_id,
            session_id="session-1",
            idempotency_key="export-1",
            export_format="csv",
        )
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"


def test_dataset_csv_export_neutralizes_formula_cells() -> None:
    assert _csv_cell("=SUM(A1)") == "'=SUM(A1)"
    assert _csv_cell("@user") == "'@user"
    assert _csv_cell("plain text") == "plain text"
