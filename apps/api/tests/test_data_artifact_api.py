from __future__ import annotations

from datetime import UTC, datetime
import base64
import json
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
from app.services.data_artifacts import (
    DataArtifactReadService,
    _csv_cell,
    _encode_cursor,
)
from app.schemas.manifest import DataType
from app.schemas.data_artifacts import DatasetArtifactCandidate
from app.schemas.data_quality import DataQualityProjection
from app.security import SecurityProblem

from data_artifact_test_support import build_input
from services.data_pipeline.data_artifacts import build_data_artifact_candidates


def _service_for_dataset() -> tuple[DataArtifactReadService, str]:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).dataset
    content = candidate.model_dump(mode="json")
    projection_payload = {
        "schema_version": "1.0.0",
        "candidate_kind": candidate.kind,
        "candidate_id": candidate.candidate_id,
        "candidate_input_hash": candidate.input_hash,
        "candidate_output_hash": candidate.output_hash,
        "candidate_content_hash": compute_canonical_payload_hash(content),
        "quality_input_hash": candidate.input_hash,
        "quality_result_id": "quality.result-1",
        "quality_result_input_hash": candidate.input_hash,
        "quality_result_output_hash": "sha256:" + "4" * 64,
        "quality_result_content_hash": "sha256:" + "5" * 64,
        "evaluation_plan_content_hash": "sha256:" + "6" * 64,
        "evaluation_commitment": "sha256:" + "7" * 64,
        "bundle_commitment": "sha256:" + "8" * 64,
        "rule_set": {
            "id": "quality.rules",
            "version": "1.0.0",
            "content_hash": "sha256:" + "9" * 64,
        },
        "research_contract": {
            "id": "contract-1",
            "version": 1,
            "content_hash": "sha256:" + "a" * 64,
        },
        "overall_status": "pass",
    }
    projection = DataQualityProjection(
        **projection_payload,
        content_hash=compute_canonical_payload_hash(projection_payload),
    )
    version_id = "version-1"
    source_identity = {
        value.source_snapshot_id: (
            value.source_id,
            value.query_hash,
            value.source_snapshot_content_hash,
        )
        for value in candidate.source_values
    }
    snapshots = tuple(
        SourceSnapshotDetail.model_construct(
            id=snapshot_id,
            source_id=source_identity[snapshot_id][0],
            source_type="fixture",
            retrieved_at=datetime.now(UTC),
            query={},
            query_hash=source_identity[snapshot_id][1],
            content_hash=source_identity[snapshot_id][2],
            license_note="fixture",
            request_metadata={},
        )
        for snapshot_id in candidate.source_snapshot_ids
    )
    transformations = {
        item.evidence_id: item for item in candidate.transformation_evidence
    }
    crossmatch_sources: dict[str, list[str]] = {}
    crossmatch_identity: dict[str, tuple[str, str]] = {}
    for transformation in transformations.values():
        for evidence_id in transformation.crossmatch_evidence_ids:
            crossmatch_sources.setdefault(evidence_id, []).append(
                transformation.locator.source_snapshot_id
            )
            crossmatch_identity[evidence_id] = (
                transformation.crossmatch_result_id,
                transformation.crossmatch_result_content_hash,
            )
    evidence_items = []
    for evidence_id in candidate.evidence_ids:
        transformation = transformations.get(evidence_id)
        if transformation is not None:
            evidence_items.append(
                EvidenceDetail.model_construct(
                    id=evidence_id,
                    artifact_version_id=version_id,
                    target_type="canonical_field",
                    target_id=transformation.canonical_field_id,
                    evidence_type="data_transformation",
                    source_snapshot_id=transformation.locator.source_snapshot_id,
                    locator=transformation.locator.model_dump(mode="json"),
                    quote_or_value=(
                        transformation.canonical_value
                        if transformation.canonical_value is not None
                        else transformation.raw_value
                    ),
                    extraction_method="data_artifact_admission",
                    confidence=1.0,
                    created_at=datetime.now(UTC),
                )
            )
            continue
        identity = crossmatch_identity[evidence_id]
        evidence_items.append(
            EvidenceDetail.model_construct(
                id=evidence_id,
                artifact_version_id=version_id,
                target_type="crossmatch",
                target_id=evidence_id,
                evidence_type="crossmatch_decision",
                source_snapshot_id=min(crossmatch_sources[evidence_id]),
                locator={
                    "crossmatch_evidence_id": evidence_id,
                    "crossmatch_result_id": identity[0],
                    "crossmatch_result_content_hash": identity[1],
                },
                quote_or_value=None,
                extraction_method="crossmatch_admission",
                confidence=1.0,
                created_at=datetime.now(UTC),
            )
        )
    evidence = tuple(evidence_items)
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
        quality_projection=projection.model_dump(mode="json"),
        quality_projection_hash=projection.content_hash,
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
        def get_version(
            self, *, version_id: str, session_id: str, full_content: bool = False
        ):
            assert version_id == version_id_value
            assert session_id == "session-1"
            return self.version

        def get_artifact(self, *, artifact_id: str, session_id: str):
            return artifact

    version_id_value = version_id
    fake = FakeArtifacts()
    fake.version = version
    return DataArtifactReadService(fake), version_id


def test_candidate_rejects_same_count_with_different_provenance_ids() -> None:
    service, _ = _service_for_dataset()
    version = service._artifacts.version
    invalid = version.model_copy(
        update={
            "source_snapshot_ids": tuple(
                "wrong-snapshot" for _ in version.source_snapshot_ids
            )
        }
    )
    with pytest.raises(SecurityProblem) as exc_info:
        service._candidate(invalid, DatasetArtifactCandidate)
    assert exc_info.value.code == "DATA_ARTIFACT_SCHEMA_INVALID"


def test_data_read_rejects_missing_or_invalid_quality_projection() -> None:
    service, version_id = _service_for_dataset()
    original = service._artifacts.version
    service._artifacts.version = original.model_copy(
        update={"quality_projection": None, "quality_projection_hash": None}
    )
    with pytest.raises(SecurityProblem) as missing:
        service.get_dataset(version_id=version_id, session_id="session-1")
    assert missing.value.code == "DATA_QUALITY_PROJECTION_REQUIRED"

    forged = dict(original.quality_projection)
    forged["content_hash"] = "sha256:" + "f" * 64
    service._artifacts.version = original.model_copy(
        update={"quality_projection": forged}
    )
    with pytest.raises(SecurityProblem) as invalid:
        service.get_dataset(version_id=version_id, session_id="session-1")
    assert invalid.value.code == "DATA_QUALITY_PROJECTION_REQUIRED"


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

    encoded = _encode_cursor(version_id=version_id, row_id=rows[0].row.row_id)
    payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    payload["ordering"] = "row_id.desc"
    tampered = (
        base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )
    with pytest.raises(SecurityProblem) as tampered_error:
        service.list_dataset_rows(
            version_id=version_id,
            session_id="session-1",
            cursor=tampered,
            limit=1,
        )
    assert tampered_error.value.code == "INVALID_CURSOR"


def test_dataset_rows_use_bounded_repository_projection() -> None:
    service, version_id = _service_for_dataset()
    candidate = DatasetArtifactCandidate.model_validate(
        service._artifacts.version.content
    )
    calls: list[tuple[str | None, int]] = []

    def list_rows(
        *, version_id: str, session_id: str, after_row_id: str | None, limit: int
    ):
        assert version_id == "version-1"
        assert session_id == "session-1"
        calls.append((after_row_id, limit))
        return tuple(row.model_dump(mode="json") for row in candidate.rows[:limit])

    service._artifacts.list_dataset_rows = list_rows
    rows, _, _ = service.list_dataset_rows(
        version_id=version_id,
        session_id="session-1",
        cursor=None,
        limit=1,
    )
    assert rows
    assert calls == [(None, 2)]


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


def test_provenance_export_includes_data_quality_attestation() -> None:
    service, version_id = _service_for_dataset()
    exported = service.create_export(
        version_id=version_id,
        session_id="session-1",
        idempotency_key="provenance-1",
        export_format="provenance_report",
    )
    payload = json.loads(exported.content)
    projection = payload["quality_projection"]
    assert projection["overall_status"] == "pass"
    assert projection["rule_set"]["content_hash"]
    assert projection["research_contract"]["content_hash"]
    assert payload["quality_projection_hash"] == projection["content_hash"]


def test_dataset_csv_export_neutralizes_formula_cells() -> None:
    assert _csv_cell("=SUM(A1)") == "'=SUM(A1)"
    assert _csv_cell("@user") == "'@user"
    assert _csv_cell("-12.5", DataType.number) == "-12.5"
    assert _csv_cell("\t=SUM(A1)") == "'\t=SUM(A1)"
    assert _csv_cell("plain text") == "plain text"
