from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Literal
from uuid import UUID

import pytest

from app.schemas.core import (
    ResearchContract,
    ResearchContractInput,
    compute_research_contract_content_hash,
)
from app.schemas.data_quality import QualityGateStatus, QualityMetricStatus
from app.workflow.scientific_admission import _validate_source_table_admission
from services.data_pipeline.source_table import (
    GAIA_SOURCE_ID,
    admit_source_table,
    replay_source_table_admission,
)


SNAPSHOT_ID = "00000000-0000-0000-0000-000000000111"
CONTENT_HASH = "sha256:" + "a" * 64
QUERY_HASH = "sha256:" + "b" * 64
RETRIEVED_AT = datetime(2026, 8, 20, 1, 2, 3, tzinfo=UTC)


def _contract() -> ResearchContract:
    contract_input = ResearchContractInput.model_validate(
        {
            "research_goal": "Admit a bounded Gaia source table",
            "target_objects": ["host_star"],
            "data_requirements": {"unit_policy": "canonical", "document_source_policy": "disabled"},
            "requested_fields": [
                "star.gaia_dr3_id",
                "system.right_ascension",
                "system.declination",
                "star.effective_temperature",
            ],
            "source_scope": {"allowed_sources": ["esa_gaia_dr3"]},
            "paper_search_scope": {},
            "output_requirements": ["dataset"],
            "evidence_requirements": {"minimum_coverage": 1},
            "quality_constraints": {
                "source_completeness_min": 1,
                "unit_consistency_min": 1,
            },
        }
    )
    payload = contract_input.model_dump(mode="json") | {
        "id": "contract.gaia",
        "project_id": "project.gaia",
        "version": 1,
        "created_from_draft_id": "draft.gaia",
        "created_at": RETRIEVED_AT,
        "content_hash": compute_research_contract_content_hash(contract_input),
    }
    return ResearchContract.model_validate(payload)


def _admit(*, result_status: Literal["complete", "empty", "truncated"] = "complete"):
    return admit_source_table(
        source_id=GAIA_SOURCE_ID,
        fields=("source_id", "ra", "dec", "teff_gspphot"),
        rows=(
            {
                "source_id": "65214061869072512",
                "ra": 56.7529935,
                "dec": 24.1081972,
                "teff_gspphot": 5720.5,
            },
        ),
        result_status=result_status,
        source_snapshot_id=SNAPSHOT_ID,
        source_snapshot_content_hash=CONTENT_HASH,
        query_hash=QUERY_HASH,
        retrieved_at=RETRIEVED_AT,
        evidence_scope_id="request.gaia.primary",
        contract=_contract(),
    )


def test_source_table_reuses_manifest_conversion_quality_and_precise_evidence() -> None:
    admitted = _admit()

    assert admitted.overall_status is QualityGateStatus.pass_
    assert admitted.rows[0].canonical_identity == "Gaia DR3 65214061869072512"
    assert admitted.rows[0].values == {
        "star.gaia_dr3_id": "Gaia DR3 65214061869072512",
        "system.right_ascension": "56.7529935",
        "system.declination": "24.1081972",
        "star.effective_temperature": "5720.5",
    }
    assert all(
        metric.status is QualityMetricStatus.determinate for metric in admitted.metrics
    )
    assert all(metric.value == 1 for metric in admitted.metrics)
    assert all(cell.locator.source_role == "single" for cell in admitted.cells)
    assert {cell.locator.raw_field for cell in admitted.cells} == {
        "source_id",
        "ra",
        "dec",
        "teff_gspphot",
    }
    assert len({cell.evidence_id for cell in admitted.cells}) == 4
    for cell in admitted.cells:
        UUID(cell.evidence_id)


@pytest.mark.parametrize("result_status", ["empty", "truncated"])
def test_incomplete_source_table_status_is_preserved_and_cannot_report_pass(
    result_status: Literal["empty", "truncated"],
) -> None:
    admitted = admit_source_table(
        source_id=GAIA_SOURCE_ID,
        fields=("source_id",),
        rows=() if result_status == "empty" else ({"source_id": "1"},),
        result_status=result_status,
        source_snapshot_id=SNAPSHOT_ID,
        source_snapshot_content_hash=CONTENT_HASH,
        query_hash=QUERY_HASH,
        retrieved_at=RETRIEVED_AT,
        evidence_scope_id="request.gaia.incomplete",
        contract=_contract(),
    )

    assert admitted.source_result_status == result_status
    assert admitted.overall_status is QualityGateStatus.insufficient
    assert all(
        metric.status is QualityMetricStatus.insufficient for metric in admitted.metrics
    )


def test_source_table_rejects_duplicate_identity_and_unpaired_coordinates() -> None:
    arguments = {
        "source_id": GAIA_SOURCE_ID,
        "result_status": "complete",
        "source_snapshot_id": SNAPSHOT_ID,
        "source_snapshot_content_hash": CONTENT_HASH,
        "query_hash": QUERY_HASH,
        "retrieved_at": RETRIEVED_AT,
        "evidence_scope_id": "request.gaia.invalid",
        "contract": _contract(),
    }
    with pytest.raises(ValueError, match="duplicate source identities"):
        admit_source_table(
            **arguments,
            fields=("source_id",),
            rows=({"source_id": "1"}, {"source_id": "Gaia DR3 1"}),
        )
    with pytest.raises(ValueError, match="coordinates must be selected as a pair"):
        admit_source_table(
            **arguments,
            fields=("source_id", "ra"),
            rows=({"source_id": "1", "ra": 56.7},),
        )


def test_source_table_public_result_cannot_drift_from_admission() -> None:
    admitted = _admit()
    evidence_ids = tuple(sorted(cell.evidence_id for cell in admitted.cells))
    candidate = SimpleNamespace(
        source_snapshot_ids=(SNAPSHOT_ID,),
        evidence_ids=evidence_ids,
        result_blocks=(
            SimpleNamespace(
                block_id="result.gaia",
                evidence_ids=evidence_ids,
                payload={"columns": [], "rows": [], "quality": {}},
            ),
        ),
        scientific_evidence=(),
    )

    with pytest.raises(ValueError, match="result payload drifted"):
        _validate_source_table_admission(candidate, _contract(), admitted)


def test_source_table_replay_rejects_self_reported_policy_drift() -> None:
    admitted = _admit()
    drifted = admitted.model_copy(update={"mapping_rule_set_version": "999.0.0"})

    with pytest.raises(ValueError, match="drifted from current frozen policies"):
        replay_source_table_admission(drifted, contract=_contract())
