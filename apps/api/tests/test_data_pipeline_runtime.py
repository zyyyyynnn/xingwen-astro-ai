from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.schemas.core import ResearchContract, compute_research_contract_content_hash
from app.schemas.enums import SourceMode
from app.schemas.manifest import ManifestBundle
from app.schemas.source_acquisition import DataSourceDataLevel
from app.workflow.data_pipeline_runtime import (
    DataPipelineAcquisitionPort,
    DataPipelineRunInput,
    DataPipelineRuntime,
)
from services.data_pipeline.manifest import load_frozen_manifest_bundle

from data_artifact_test_support import build_input


PROJECT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
RUN_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _contract(
    *, project_id: UUID = PROJECT_ID, source_min: float = 1.0
) -> ResearchContract:
    payload = {
        "id": "rc_data_pipeline_runtime",
        "project_id": str(project_id),
        "version": 1,
        "research_goal": "Prepare an evidence-bound exoplanet dataset",
        "target_objects": ["exoplanet_candidate", "host_star"],
        "data_requirements": {"unit_policy": "canonical"},
        "requested_fields": ["star.tic_id"],
        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
        "paper_search_scope": {"max_candidates": 20},
        "output_requirements": ["dataset"],
        "evidence_requirements": {
            "require_locator": True,
            "require_source_snapshot": True,
            "minimum_coverage": 1.0,
        },
        "quality_constraints": {
            "source_completeness_min": source_min,
            "unit_consistency_min": 1.0,
        },
        "created_from_draft_id": "rcd_data_pipeline_runtime",
        "created_at": datetime(2026, 8, 14, tzinfo=timezone.utc),
        "content_hash": "sha256:" + "0" * 64,
    }
    payload["content_hash"] = compute_research_contract_content_hash(payload)
    return ResearchContract.model_validate(payload)


def _request(
    left_right,
    *,
    contract: ResearchContract | None = None,
    acquisitions=None,
) -> DataPipelineRunInput:
    return DataPipelineRunInput(
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        step_key="cleaning_data",
        contract=contract or _contract(),
        acquisitions=acquisitions or left_right,
    )


class _FakeAcquisition(DataPipelineAcquisitionPort):
    def __init__(self, acquisitions, tic_ids: tuple[str, ...] = ("123", "456")) -> None:
        self.acquisitions = acquisitions
        self.tic_ids = tic_ids
        self.discovered_calls = 0
        self.acquired_calls: list[tuple[str, ...]] = []

    def discover_nearby_confirmed_tic_ids(self) -> tuple[str, ...]:
        self.discovered_calls += 1
        return self.tic_ids

    def acquire(
        self,
        *,
        manifests: ManifestBundle,
        tic_ids: tuple[str, ...],
    ):
        assert manifests.case_manifest.case_id
        self.acquired_calls.append(tic_ids)
        return self.acquisitions


def test_prepare_reuses_authoritative_crossmatch_mapping_and_quality_pipeline() -> None:
    source_input = build_input("star.tic_id")
    manifests = load_frozen_manifest_bundle()
    runtime = DataPipelineRuntime(manifests)
    prepared = runtime.prepare(
        _request(
            (source_input.left_acquisition, source_input.right_acquisition),
            acquisitions=(
                source_input.left_acquisition,
                source_input.right_acquisition,
            ),
        )
    )

    assert prepared.step_key == "cleaning_data"
    assert prepared.project_id == PROJECT_ID
    assert prepared.run_id == RUN_ID
    assert prepared.data_input.requested_fields == ("star.tic_id",)
    assert prepared.build_result.dataset.__artifact_publication_is_admitted__()
    assert prepared.quality_result.contract_gate.overall_status.value == "pass"
    assert tuple(item.kind for item in prepared.artifacts) == (
        "dataset",
        "field_dictionary",
        "source_collection",
    )
    assert all(item.source_snapshot_bindings for item in prepared.artifacts)
    assert all(item.evidence_bindings for item in prepared.artifacts)


def test_prepare_can_produce_the_existing_publisher_dataset_admission() -> None:
    source_input = build_input("star.tic_id")
    runtime = DataPipelineRuntime(load_frozen_manifest_bundle())
    prepared = runtime.prepare(
        _request(
            (source_input.left_acquisition, source_input.right_acquisition),
            acquisitions=(
                source_input.left_acquisition,
                source_input.right_acquisition,
            ),
        )
    )

    admitted = runtime.admit_dataset(prepared)

    assert admitted.content_hash.startswith("sha256:")
    assert tuple(admitted.source_snapshot_ids) == tuple(
        item.persisted_source_snapshot_id
        for item in prepared.artifacts[0].source_snapshot_bindings
    )
    assert len(admitted.data_evidence_materializations) == len(
        prepared.dataset.evidence_ids
    )


def test_live_acquisition_is_explicit_and_target_ids_are_fail_closed() -> None:
    source_input = build_input("star.tic_id")
    fake = _FakeAcquisition(
        (source_input.left_acquisition, source_input.right_acquisition),
    )
    runtime = DataPipelineRuntime(load_frozen_manifest_bundle(), acquisition=fake)

    acquisitions = runtime.acquire_live_data()

    assert acquisitions[0].source_mode is SourceMode.fixture
    assert acquisitions[1].data_level is DataSourceDataLevel.fixture
    assert fake.discovered_calls == 1
    assert fake.acquired_calls == [("123", "456")]

    duplicate = _FakeAcquisition(
        (source_input.left_acquisition, source_input.right_acquisition),
        tic_ids=("123", "123"),
    )
    with pytest.raises(ValueError, match="唯一"):
        DataPipelineRuntime(
            load_frozen_manifest_bundle(), acquisition=duplicate
        ).acquire_live_data()
    assert duplicate.acquired_calls == []


def test_prepare_rejects_quality_insufficient_data_before_publication() -> None:
    source_input = build_input("star.tic_id", scenario_id="truncated_inconclusive")
    runtime = DataPipelineRuntime(load_frozen_manifest_bundle())

    with pytest.raises(ValueError, match="quality gate"):
        runtime.prepare(
            _request(
                (source_input.left_acquisition, source_input.right_acquisition),
                acquisitions=(
                    source_input.left_acquisition,
                    source_input.right_acquisition,
                ),
            )
        )


def test_run_and_contract_project_identity_are_checked_without_run_state_access() -> (
    None
):
    source_input = build_input("star.tic_id")
    foreign_contract = _contract(
        project_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    )

    with pytest.raises(ValueError, match="owned by"):
        _request(
            (source_input.left_acquisition, source_input.right_acquisition),
            contract=foreign_contract,
            acquisitions=(
                source_input.left_acquisition,
                source_input.right_acquisition,
            ),
        )
