from __future__ import annotations

import pytest

from app.workflow.publisher import PublicationAdmissionError, admit_artifact_candidate
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
