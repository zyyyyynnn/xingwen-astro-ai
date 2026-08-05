from __future__ import annotations

import pytest
from pydantic import ValidationError
from types import SimpleNamespace
from uuid import uuid4

from app.workflow.publisher import (
    ArtifactPublication,
    PublicationAdmissionError,
    PublicationConflictError,
    _require_same_publication,
    admit_artifact_candidate,
)
from services.data_pipeline.data_artifacts.admission import (
    validate_data_artifact_domain,
    validate_data_artifact_evidence,
)
from services.data_pipeline.data_quality import (
    admit_data_artifact_quality,
    build_data_quality_publication_validator,
    evaluate_data_quality,
)

from test_data_quality_pipeline import make_quality_input


def _quality_admission():
    quality_input, build_result = make_quality_input("star.tic_id")
    quality_result = evaluate_data_quality(quality_input)
    admitted = admit_data_artifact_quality(
        build_result=build_result,
        evaluation_input=quality_input,
        evaluation_result=quality_result,
    )
    return admitted, build_result


def test_real_publisher_port_accepts_each_exact_c04_candidate_with_c05_gate() -> None:
    admitted, build_result = _quality_admission()

    admitted_candidates = []
    for kind, candidate in (
        ("dataset", build_result.dataset),
        ("field_dictionary", build_result.field_dictionary),
        ("source_collection", build_result.source_collection),
    ):
        admitted_candidates.append(
            admit_artifact_candidate(
                candidate,
                schema_version=candidate.schema_version,
                source_snapshot_ids=candidate.source_snapshot_ids,
                evidence_ids=candidate.evidence_ids,
                evidence_validator=validate_data_artifact_evidence,
                domain_validator=validate_data_artifact_domain,
                quality_validator=build_data_quality_publication_validator(
                    admitted,
                    candidate_kind=kind,
                ),
            )
        )

    assert tuple(item.content["kind"] for item in admitted_candidates) == (
        "dataset",
        "field_dictionary",
        "source_collection",
    )
    for candidate in admitted_candidates:
        projection = candidate.quality_projection
        assert projection is not None
        assert projection.quality_result_id == admitted.evaluation_result.result_id
        assert projection.candidate_content_hash == candidate.content_hash
        assert projection.overall_status == "pass"
        assert projection.evaluation_commitment == admitted.snapshot.evaluation_commitment
        assert projection.rule_set.content_hash == admitted.snapshot.rule_set_content_hash
        assert projection.research_contract.content_hash == admitted.snapshot.contract_content_hash
        with pytest.raises(ValidationError):
            projection.rule_set.content_hash = "sha256:" + "f" * 64

    candidate = admitted_candidates[0]
    run_id, step_id, attempt_id, artifact_id, producer_id = (
        uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    )
    publication = ArtifactPublication(
        artifact_id=artifact_id,
        publication_key="quality-replay",
        producer_execution_id=producer_id,
        candidate=candidate,
        source_mode="fixture",
    )
    stored = SimpleNamespace(
        artifact_id=artifact_id,
        created_by_run_id=run_id,
        run_step_id=step_id,
        step_attempt_id=attempt_id,
        producer_execution_id=producer_id,
        publication_key="quality-replay",
        schema_version=candidate.schema_version,
        content=candidate.content,
        content_hash=candidate.content_hash,
        source_mode="fixture",
        source_snapshot_ids=list(candidate.source_snapshot_ids),
        evidence_ids=list(candidate.evidence_ids),
        quality_projection={"forged": True},
        quality_projection_hash=candidate.quality_projection_hash,
        supersedes_version_id=None,
    )
    with pytest.raises(PublicationConflictError):
        _require_same_publication(
            stored,
            run_id=run_id,
            step_id=step_id,
            attempt_id=attempt_id,
            output=publication,
        )


def test_reparsed_or_foreign_candidate_cannot_use_c05_admission() -> None:
    admitted, build_result = _quality_admission()
    foreign_input, foreign_result = make_quality_input("planet.name")
    validator = build_data_quality_publication_validator(admitted, candidate_kind="dataset")

    with pytest.raises(PublicationAdmissionError, match="Artifact candidate admission failed"):
        admit_artifact_candidate(
            foreign_result.dataset,
            schema_version=foreign_result.dataset.schema_version,
            source_snapshot_ids=foreign_result.dataset.source_snapshot_ids,
            evidence_ids=foreign_result.dataset.evidence_ids,
            evidence_validator=validate_data_artifact_evidence,
            domain_validator=validate_data_artifact_domain,
            quality_validator=validator,
        )

    assert foreign_input.dataset_candidate is not build_result.dataset


def test_self_consistent_public_projection_cannot_forge_c05_capability() -> None:
    admitted, build_result = _quality_admission()
    trusted = build_data_quality_publication_validator(
        admitted,
        candidate_kind="dataset",
    )

    def forged_validator(_context) -> None:
        return None

    forged_validator.quality_projection = trusted._data_quality_attestation.projection_json
    with pytest.raises(PublicationAdmissionError, match="C-05 attestation"):
        admit_artifact_candidate(
            build_result.dataset,
            schema_version=build_result.dataset.schema_version,
            source_snapshot_ids=build_result.dataset.source_snapshot_ids,
            evidence_ids=build_result.dataset.evidence_ids,
            evidence_validator=validate_data_artifact_evidence,
            domain_validator=validate_data_artifact_domain,
            quality_validator=forged_validator,
        )
