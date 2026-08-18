from __future__ import annotations

import pytest

from app.schemas.data_artifacts import DatasetArtifactCandidate
from app.workflow.publisher import PublicationAdmissionError, admit_artifact_candidate
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.data_artifacts.admission import (
    validate_data_artifact_domain,
    validate_data_artifact_evidence,
    validate_data_artifact_quality_prerequisites,
)

from data_artifact_test_support import build_data_publication_bindings, build_input


def _admit(candidate):
    snapshots, evidence = build_data_publication_bindings(candidate)
    return admit_artifact_candidate(
        candidate,
        schema_version=candidate.schema_version,
        source_snapshot_ids=candidate.source_snapshot_ids,
        evidence_ids=candidate.evidence_ids,
        evidence_validator=validate_data_artifact_evidence,
        domain_validator=validate_data_artifact_domain,
        quality_validator=validate_data_artifact_quality_prerequisites,
        source_snapshot_bindings=snapshots,
        evidence_bindings=evidence,
    )


def test_data_artifact_prerequisites_cannot_bypass_final_data_quality_publication_gate() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))

    with pytest.raises(
        PublicationAdmissionError,
        match="Data Quality Evaluation attestation",
    ):
        _admit(result.dataset)
    for candidate in (result.field_dictionary, result.source_collection):
        with pytest.raises(
            PublicationAdmissionError,
            match="requires its exact paired Dataset provenance",
        ):
            admit_artifact_candidate(
                candidate,
                schema_version=candidate.schema_version,
                source_snapshot_ids=candidate.source_snapshot_ids,
                evidence_ids=candidate.evidence_ids,
                evidence_validator=validate_data_artifact_evidence,
                domain_validator=validate_data_artifact_domain,
                quality_validator=validate_data_artifact_quality_prerequisites,
            )


def test_reparsed_copied_and_intermediate_candidates_cannot_bypass_port() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))
    reparsed = DatasetArtifactCandidate.model_validate(
        result.dataset.model_dump(mode="json")
    )
    copied = result.dataset.model_copy()

    for candidate in (reparsed, copied):
        with pytest.raises(PublicationAdmissionError, match="cannot bypass"):
            _admit(candidate)

    with pytest.raises(PublicationAdmissionError, match="cannot bypass"):
        admit_artifact_candidate(
            result,
            schema_version=result.schema_version,
            source_snapshot_ids=result.dataset.source_snapshot_ids,
            evidence_ids=result.dataset.evidence_ids,
            evidence_validator=validate_data_artifact_evidence,
            domain_validator=validate_data_artifact_domain,
            quality_validator=validate_data_artifact_quality_prerequisites,
        )


@pytest.mark.parametrize("candidate", ({"kind": "dataset"}, "free text"))
def test_untyped_content_is_rejected_before_data_artifact_validators(candidate) -> None:
    with pytest.raises(PublicationAdmissionError, match="validated Pydantic"):
        admit_artifact_candidate(
            candidate,
            schema_version="1.0.0",
            source_snapshot_ids=("snapshot.one",),
            evidence_ids=("evidence.one",),
            evidence_validator=validate_data_artifact_evidence,
            domain_validator=validate_data_artifact_domain,
            quality_validator=validate_data_artifact_quality_prerequisites,
        )
