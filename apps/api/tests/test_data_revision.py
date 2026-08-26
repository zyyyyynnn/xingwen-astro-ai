"""Selective data-revision domain execution through one stable interface."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.schemas.core import ArtifactKind
from app.schemas.enums import SourceMode
from app.schemas.source_acquisition import DataSourceDataLevel
from app.schemas.crossmatch import (
    CrossmatchInput,
    CrossmatchRuleSet,
    compute_crossmatch_content_hash,
    compute_crossmatch_input_hash,
    compute_crossmatch_source_input_hash,
)
from app.schemas.data_artifacts import (
    CrossmatchDataArtifactAuthority,
    compute_data_artifact_content_hash,
    compute_data_artifact_public_payload_hash,
)
from app.schemas.manifest import load_manifest_bundle
from data_artifact_test_support import build_input
from app.workflow.data_artifact_publication import (
    DataArtifactPublicationConfig,
    DataArtifactPublicationService,
    PreparedDataArtifacts,
)
from app.workflow.steps import data_steps as data_steps_module
from app.workflow.steps.data_steps import DataStepService
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.data_artifacts import projection as projection_module
from services.data_pipeline import source_table as source_table_module
from services.data_pipeline.crossmatch import align_cross_source_records
from services.data_pipeline.revision import (
    DataRevisionArtifactBaseline,
    DataRevisionError,
    DataRevisionExecutionInput,
    DataRevisionExecutionResult,
    execute_data_revision,
)
from test_data_quality_source_table import _source_table_data_input
from test_source_table_admission import _contract as source_table_contract


HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
_ROOT = Path(__file__).resolve().parents[3]


def _versioned(value: object, **updates: object) -> object:
    payload = value.model_dump(mode="json")  # type: ignore[attr-defined]
    payload.update(updates)
    payload.pop("content_hash", None)
    payload["content_hash"] = (
        compute_crossmatch_content_hash(payload)
        if isinstance(value, CrossmatchRuleSet)
        else compute_data_artifact_content_hash(payload)
    )
    return type(value).model_validate(payload)


def _execution_input(
    *,
    scenario: str,
) -> tuple[DataRevisionExecutionInput, list[str]]:
    baseline_input = build_input("star.tic_id")
    baseline_result = build_data_artifact_candidates(baseline_input)
    candidates = {
        "dataset": baseline_result.dataset,
        "field_dictionary": baseline_result.field_dictionary,
        "source_collection": baseline_result.source_collection,
    }
    baselines = tuple(
        DataRevisionArtifactBaseline(
            artifact_kind=kind,
            artifact_id=uuid4(),
            baseline_version_id=uuid4(),
            version_number=1,
            decision="reuse" if scenario == "unaffected" else "recompute",
            step_key=None if scenario == "unaffected" else "cleaning_data",
            candidate_content_hash=compute_data_artifact_public_payload_hash(
                candidate
            ),
        )
        for kind, candidate in candidates.items()
    )
    authority = baseline_input.authority
    context = authority.crossmatch_result.admission_context
    mapping = baseline_input.mapping_rule_set
    conversion = baseline_input.conversion_catalog
    quality_hash = HASH_A
    acquisition_calls: list[str] = []

    if scenario == "mapping":
        mapping = _versioned(
            mapping,
            version="9.9.9",
            producer_version="9.9.9",
        )
    elif scenario == "unit":
        conversion = _versioned(conversion, version="9.9.9")
    elif scenario == "crossmatch":
        context = context.model_copy(
            update={
                "rule_set": _versioned(context.rule_set, version="9.9.9"),
            }
        )
    elif scenario == "quality":
        quality_hash = HASH_B

    def acquire_sources():
        acquisition_calls.append("source")
        return authority.left_acquisition, authority.right_acquisition

    def align_authority(left, right):
        payload = {
            "case_manifest_id": baseline_input.manifest_pins.case_manifest_id,
            "case_manifest_version": baseline_input.manifest_pins.case_manifest_version,
            "case_manifest_content_hash": baseline_input.manifest_pins.case_manifest_content_hash,
            "field_manifest_id": baseline_input.manifest_pins.field_manifest_id,
            "field_manifest_version": baseline_input.manifest_pins.field_manifest_version,
            "field_manifest_content_hash": baseline_input.manifest_pins.field_manifest_content_hash,
            "rule_set": context.rule_set.model_dump(mode="json"),
            "alias_catalog": context.alias_catalog.model_dump(mode="json"),
            "source_policy": context.source_policy.model_dump(mode="json"),
            "left": left.model_dump(mode="json"),
            "right": right.model_dump(mode="json"),
            "manual_review_decisions": (),
        }
        payload["source_input_hash"] = compute_crossmatch_source_input_hash(payload)
        payload["input_hash"] = compute_crossmatch_input_hash(payload)
        return CrossmatchDataArtifactAuthority(
            left_acquisition=left,
            right_acquisition=right,
            crossmatch_result=align_cross_source_records(
                CrossmatchInput.model_validate(payload)
            ),
            document_observations=(),
        )

    return (
        DataRevisionExecutionInput(
            plan_hash=HASH_A,
            baselines=baselines,
            baseline_input=baseline_input,
            baseline_result=baseline_result,
            baseline_quality_rule_set_content_hash=HASH_A,
            current_mapping_rule_set=mapping,
            current_conversion_catalog=conversion,
            current_crossmatch_rule_set=context.rule_set,
            current_alias_catalog=context.alias_catalog,
            current_source_policy=context.source_policy,
            current_quality_rule_set_content_hash=quality_hash,
            baseline_source_mode=authority.left_acquisition.source_mode,
            acquisition_recompute_authorized=scenario == "source",
            acquire_sources=acquire_sources,
            align_crossmatch_authority=align_authority,
        ),
        acquisition_calls,
    )


@pytest.mark.parametrize(
    ("scenario", "expected_stages"),
    (
        ("source", ("source", "mapping_unit", "quality")),
        ("crossmatch", ("crossmatch", "mapping_unit", "quality")),
        ("mapping", ("mapping_unit", "quality")),
        ("unit", ("mapping_unit", "quality")),
        ("quality", ("quality",)),
        ("unaffected", ()),
    ),
)
def test_selective_revision_executes_only_the_authorized_stage_closure(
    scenario: str,
    expected_stages: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_input, acquisition_calls = _execution_input(scenario=scenario)
    monkeypatch.setattr(
        projection_module,
        "load_mapping_rule_set",
        lambda: execution_input.current_mapping_rule_set,
    )
    monkeypatch.setattr(
        projection_module,
        "load_unit_conversion_catalog",
        lambda: execution_input.current_conversion_catalog,
    )
    monkeypatch.setattr(
        projection_module,
        "load_crossmatch_rule_set",
        lambda: execution_input.current_crossmatch_rule_set,
    )
    monkeypatch.setattr(
        projection_module,
        "load_entity_alias_catalog",
        lambda: execution_input.current_alias_catalog,
    )
    monkeypatch.setattr(
        projection_module,
        "load_crossmatch_source_policy",
        lambda: execution_input.current_source_policy,
    )

    first = execute_data_revision(execution_input)
    second = execute_data_revision(execution_input)

    assert first.required_stages == expected_stages
    assert second.required_stages == expected_stages
    assert acquisition_calls == (["source", "source"] if scenario == "source" else [])
    if scenario == "unaffected":
        assert first.disposition == "reuse"
        assert first.build_result is None
        assert first.publication_targets == ()
        return

    assert first.disposition == "recompute"
    assert first.build_result is not None
    assert second.build_result is not None
    assert (
        first.build_result.dataset.candidate_id,
        first.build_result.dataset.canonical_content_hash,
        first.build_result.dataset.lineage_hash,
        first.build_result.field_dictionary.candidate_id,
        first.build_result.source_collection.candidate_id,
    ) == (
        second.build_result.dataset.candidate_id,
        second.build_result.dataset.canonical_content_hash,
        second.build_result.dataset.lineage_hash,
        second.build_result.field_dictionary.candidate_id,
        second.build_result.source_collection.candidate_id,
    )
    assert tuple(target.artifact_kind for target in first.publication_targets) == (
        "dataset",
        "field_dictionary",
        "source_collection",
    )
    assert all(
        target.supersedes_version_id == target.baseline_version_id
        for target in first.publication_targets
    )
    if scenario == "quality":
        assert first.build_result.model_dump(mode="json") == (
            execution_input.baseline_result.model_dump(mode="json")
        )


def test_unstructured_affected_revision_requires_replan() -> None:
    execution_input, _ = _execution_input(scenario="quality")
    unchanged = replace(
        execution_input,
        current_quality_rule_set_content_hash=(
            execution_input.baseline_quality_rule_set_content_hash
        ),
    )

    with pytest.raises(DataRevisionError, match="REVISION_DATA_REPLAN_REQUIRED"):
        execute_data_revision(unchanged)


def test_candidate_reuse_failure_falls_back_to_authorized_complete_rebuild() -> None:
    execution_input, _ = _execution_input(scenario="quality")
    incompatible = replace(
        execution_input,
        baselines=(
            replace(execution_input.baselines[0], candidate_content_hash=HASH_B),
            *execution_input.baselines[1:],
        ),
    )

    result = execute_data_revision(incompatible)

    assert result.disposition == "recompute"
    assert result.required_stages == ("mapping_unit", "quality")
    assert result.data_input == execution_input.baseline_input
    assert result.build_result is not None
    assert result.build_result.model_dump(mode="json") == (
        execution_input.baseline_result.model_dump(mode="json")
    )


def test_fixture_quality_revision_preserves_publication_provenance_without_acquisition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_input, acquisition_calls = _execution_input(scenario="quality")
    execution_input = replace(
        execution_input,
        baseline_source_mode=SourceMode.fixture,
    )
    monkeypatch.setattr(
        projection_module,
        "load_mapping_rule_set",
        lambda: execution_input.current_mapping_rule_set,
    )
    monkeypatch.setattr(
        projection_module,
        "load_unit_conversion_catalog",
        lambda: execution_input.current_conversion_catalog,
    )
    monkeypatch.setattr(
        projection_module,
        "load_crossmatch_rule_set",
        lambda: execution_input.current_crossmatch_rule_set,
    )
    monkeypatch.setattr(
        projection_module,
        "load_entity_alias_catalog",
        lambda: execution_input.current_alias_catalog,
    )
    monkeypatch.setattr(
        projection_module,
        "load_crossmatch_source_policy",
        lambda: execution_input.current_source_policy,
    )
    captured_configs: list[DataArtifactPublicationConfig] = []

    class DataArtifacts:
        def prepare(self, _context, **kwargs):
            captured_configs.append(kwargs["config"])
            return SimpleNamespace(
                build_result=kwargs["build_result"],
                quality=SimpleNamespace(evaluation_result=SimpleNamespace()),
                executions={},
            )

        def publish(self, _context, **_kwargs):
            return ()

    service = object.__new__(DataStepService)
    service._data_artifacts = DataArtifacts()  # type: ignore[attr-defined]
    context = SimpleNamespace(
        run_id=uuid4(),
        data_revision=execution_input,
        data_acquisitions=None,
    )

    prepared = service._clean_revision(  # type: ignore[arg-type]
        context,
        step_key="cleaning_data",
        attempt=SimpleNamespace(),
        lease=SimpleNamespace(),
    )

    assert prepared.publications == ()
    assert acquisition_calls == []
    assert len(captured_configs) == 1
    assert captured_configs[0].source_mode is SourceMode.fixture


def test_fixture_revision_publishes_actual_live_reacquisition_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_input, _ = _execution_input(scenario="source")
    baseline_authority = execution_input.baseline_input.authority
    assert isinstance(baseline_authority, CrossmatchDataArtifactAuthority)

    def live_source(source):
        metadata = {
            **source.snapshot.request_metadata,
            "source_mode": SourceMode.live.value,
            "data_level": DataSourceDataLevel.live_result.value,
        }
        return source.model_copy(
            update={
                "source_mode": SourceMode.live,
                "data_level": DataSourceDataLevel.live_result,
                "snapshot": source.snapshot.model_copy(
                    update={"request_metadata": metadata}
                ),
            }
        )

    live_acquisitions = (
        live_source(baseline_authority.left_acquisition),
        live_source(baseline_authority.right_acquisition),
    )
    execution_input = replace(
        execution_input,
        baseline_source_mode=SourceMode.fixture,
    )
    monkeypatch.setattr(
        projection_module,
        "load_mapping_rule_set",
        lambda: execution_input.current_mapping_rule_set,
    )
    monkeypatch.setattr(
        projection_module,
        "load_unit_conversion_catalog",
        lambda: execution_input.current_conversion_catalog,
    )
    monkeypatch.setattr(
        projection_module,
        "load_crossmatch_rule_set",
        lambda: execution_input.current_crossmatch_rule_set,
    )
    monkeypatch.setattr(
        projection_module,
        "load_entity_alias_catalog",
        lambda: execution_input.current_alias_catalog,
    )
    monkeypatch.setattr(
        projection_module,
        "load_crossmatch_source_policy",
        lambda: execution_input.current_source_policy,
    )
    captured_configs: list[DataArtifactPublicationConfig] = []

    class DataArtifacts:
        def prepare(self, _context, **kwargs):
            captured_configs.append(kwargs["config"])
            return SimpleNamespace(
                build_result=kwargs["build_result"],
                quality=SimpleNamespace(evaluation_result=SimpleNamespace()),
                executions={},
            )

        def publish(self, _context, **_kwargs):
            return ()

    service = object.__new__(DataStepService)
    service._manifests = load_manifest_bundle(  # type: ignore[attr-defined]
        _ROOT
        / "services/data_pipeline/manifests/exoplanet_host_star/case-manifest.json",
        _ROOT
        / "services/data_pipeline/manifests/exoplanet_host_star/field-manifest.json",
    )
    service._data_artifacts = DataArtifacts()  # type: ignore[attr-defined]
    service._store = SimpleNamespace(  # type: ignore[attr-defined]
        repair_checkpoint_decision=lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(service, "_admit_document_observations", lambda *_a, **_k: None)
    monkeypatch.setattr(data_steps_module, "derive_repair_defects", lambda *_a, **_k: ())
    context = SimpleNamespace(
        run_id=uuid4(),
        data_revision=execution_input,
        data_acquisitions=live_acquisitions,
        contract=SimpleNamespace(),
    )

    service._clean_revision(  # type: ignore[arg-type]
        context,
        step_key="cleaning_data",
        attempt=SimpleNamespace(),
        lease=SimpleNamespace(),
    )

    assert len(captured_configs) == 1
    assert captured_configs[0].source_mode is SourceMode.live


def test_source_table_mapping_drift_rebuilds_from_raw_authority_without_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template, _ = _execution_input(scenario="mapping")
    baseline_input = _source_table_data_input()
    baseline_result = build_data_artifact_candidates(baseline_input)
    candidates = {
        "dataset": baseline_result.dataset,
        "field_dictionary": baseline_result.field_dictionary,
        "source_collection": baseline_result.source_collection,
    }
    mapping = _versioned(
        baseline_input.mapping_rule_set,
        version="9.9.9",
        producer_version="9.9.9",
    )
    provider_calls: list[str] = []
    execution_input = replace(
        template,
        baselines=tuple(
            DataRevisionArtifactBaseline(
                artifact_kind=kind,
                artifact_id=uuid4(),
                baseline_version_id=uuid4(),
                version_number=1,
                decision="recompute",
                step_key="analyzing_data",
                candidate_content_hash=compute_data_artifact_public_payload_hash(
                    candidate
                ),
            )
            for kind, candidate in candidates.items()
        ),
        baseline_input=baseline_input,
        baseline_result=baseline_result,
        baseline_quality_rule_set_content_hash=(
            baseline_input.authority.source_table_admission.quality_rule_set_content_hash
        ),
        current_mapping_rule_set=mapping,
        current_conversion_catalog=baseline_input.conversion_catalog,
        current_quality_rule_set_content_hash=(
            baseline_input.authority.source_table_admission.quality_rule_set_content_hash
        ),
        baseline_source_mode=SourceMode.fixture,
        acquisition_recompute_authorized=False,
        acquire_source_table_input=lambda: (
            provider_calls.append("provider"),
            SourceMode.live,
        ),  # type: ignore[arg-type]
        research_contract=source_table_contract(),
    )
    monkeypatch.setattr(source_table_module, "load_mapping_rule_set", lambda: mapping)
    monkeypatch.setattr(projection_module, "load_mapping_rule_set", lambda: mapping)
    monkeypatch.setattr(
        projection_module,
        "load_unit_conversion_catalog",
        lambda: baseline_input.conversion_catalog,
    )

    result = execute_data_revision(execution_input)

    assert provider_calls == []
    assert result.required_stages == ("mapping_unit", "quality")
    assert result.data_input is not None
    assert result.build_result is not None
    authority = result.data_input.authority
    assert authority.source_table_admission.mapping_rule_set_content_hash == (
        mapping.content_hash
    )
    assert tuple(target.artifact_kind for target in result.publication_targets) == (
        "dataset",
        "field_dictionary",
        "source_collection",
    )


def test_source_table_insufficient_raw_authority_requires_replan_before_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template, _ = _execution_input(scenario="mapping")
    baseline_input = _source_table_data_input()
    baseline_result = build_data_artifact_candidates(baseline_input)
    admission = baseline_input.authority.source_table_admission
    incomplete_admission = admission.model_copy(update={"cells": admission.cells[:-1]})
    incomplete_input = baseline_input.model_copy(
        update={
            "authority": baseline_input.authority.model_copy(
                update={"source_table_admission": incomplete_admission}
            )
        }
    )
    mapping = _versioned(
        baseline_input.mapping_rule_set,
        version="9.9.9",
        producer_version="9.9.9",
    )
    candidates = {
        "dataset": baseline_result.dataset,
        "field_dictionary": baseline_result.field_dictionary,
        "source_collection": baseline_result.source_collection,
    }
    provider_calls: list[str] = []
    execution_input = replace(
        template,
        baselines=tuple(
            DataRevisionArtifactBaseline(
                artifact_kind=kind,
                artifact_id=uuid4(),
                baseline_version_id=uuid4(),
                version_number=1,
                decision="recompute",
                step_key="analyzing_data",
                candidate_content_hash=compute_data_artifact_public_payload_hash(
                    candidate
                ),
            )
            for kind, candidate in candidates.items()
        ),
        baseline_input=incomplete_input,
        baseline_result=baseline_result,
        baseline_quality_rule_set_content_hash=admission.quality_rule_set_content_hash,
        current_mapping_rule_set=mapping,
        current_conversion_catalog=baseline_input.conversion_catalog,
        current_quality_rule_set_content_hash=admission.quality_rule_set_content_hash,
        baseline_source_mode=SourceMode.fixture,
        acquisition_recompute_authorized=False,
        acquire_source_table_input=lambda: (
            provider_calls.append("provider") or baseline_input,
            SourceMode.live,
        ),
        research_contract=source_table_contract(),
    )
    monkeypatch.setattr(source_table_module, "load_mapping_rule_set", lambda: mapping)

    with pytest.raises(DataRevisionError, match="REVISION_DATA_REPLAN_REQUIRED"):
        execute_data_revision(execution_input)

    assert provider_calls == []


def test_all_reuse_requires_exact_candidate_compatibility() -> None:
    execution_input, _ = _execution_input(scenario="unaffected")
    incompatible = replace(
        execution_input,
        baselines=(
            replace(execution_input.baselines[0], candidate_content_hash=HASH_B),
            *execution_input.baselines[1:],
        ),
    )

    with pytest.raises(DataRevisionError, match="REVISION_DATA_REPLAN_REQUIRED"):
        execute_data_revision(incompatible)


def test_revision_publication_requires_explicit_revision_targets() -> None:
    execution_input, _ = _execution_input(scenario="quality")
    assert execution_input.baseline_result is not None
    failures: list[tuple[str, str, str]] = []

    class Publications:
        def finish_producer(
            self,
            execution_id: str,
            *,
            status: str,
            error_code: str,
        ) -> None:
            failures.append((execution_id, status, error_code))

    service = DataArtifactPublicationService(  # type: ignore[arg-type]
        Publications(),
        SimpleNamespace(),
    )
    prepared = PreparedDataArtifacts(
        build_result=execution_input.baseline_result,
        quality=SimpleNamespace(),  # type: ignore[arg-type]
        executions={
            kind: SimpleNamespace(id=kind)
            for kind in ("dataset", "field_dictionary", "source_collection")
        },  # type: ignore[arg-type]
    )
    config = DataArtifactPublicationConfig(
        publish_kinds=(
            ArtifactKind.dataset,
            ArtifactKind.field_dictionary,
            ArtifactKind.source_collection,
        ),
        operation_key_prefix="revision-test",
        producer_error_code="REVISION_TEST_FAILED",
        producer_version="1.0.0",
        quality_failure_message="unused",
    )

    with pytest.raises(
        ValueError,
        match="revision data publication requires explicit revision targets",
    ):
        service.publish(  # type: ignore[arg-type]
            SimpleNamespace(data_revision=execution_input),
            prepared=prepared,
            config=config,
        )

    assert failures == [
        ("dataset", "failed", "REVISION_TEST_FAILED"),
        ("field_dictionary", "failed", "REVISION_TEST_FAILED"),
        ("source_collection", "failed", "REVISION_TEST_FAILED"),
    ]


def test_changed_crossmatch_uses_repair_seam_and_readmits_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_input, _ = _execution_input(scenario="crossmatch")
    baseline_authority = execution_input.baseline_input.authority
    assert isinstance(baseline_authority, CrossmatchDataArtifactAuthority)
    baseline_with_documents = execution_input.baseline_input.model_copy(
        update={
            "authority": baseline_authority.model_copy(
                update={"document_observations": ("frozen-old-observation",)}
            )
        }
    )
    revision = replace(execution_input, baseline_input=baseline_with_documents)
    checkpoint_queries: list[tuple[object, str]] = []

    class Store:
        def repair_checkpoint_decision(
            self, run_id: object, *, step_key: str
        ) -> None:
            checkpoint_queries.append((run_id, step_key))
            return None

    service = object.__new__(DataStepService)
    service._manifests = load_manifest_bundle(  # type: ignore[attr-defined]
        _ROOT
        / "services/data_pipeline/manifests/exoplanet_host_star/case-manifest.json",
        _ROOT
        / "services/data_pipeline/manifests/exoplanet_host_star/field-manifest.json",
    )
    service._store = Store()  # type: ignore[attr-defined]
    admitted_crossmatches: list[object] = []

    def admit_documents(
        _context: object,
        *,
        crossmatch: object,
        **_kwargs: object,
    ) -> None:
        admitted_crossmatches.append(crossmatch)
        return None

    monkeypatch.setattr(service, "_admit_document_observations", admit_documents)
    monkeypatch.setattr(data_steps_module, "derive_repair_defects", lambda *_args, **_kwargs: ())
    returned_authorities: list[CrossmatchDataArtifactAuthority] = []

    def execute_with_changed_crossmatch(value):
        assert value.align_crossmatch_authority is not None
        authority = value.align_crossmatch_authority(
            baseline_authority.left_acquisition,
            baseline_authority.right_acquisition,
        )
        returned_authorities.append(authority)
        return DataRevisionExecutionResult("reuse", (), None, None, ())

    monkeypatch.setattr(
        data_steps_module,
        "execute_data_revision",
        execute_with_changed_crossmatch,
    )
    context = SimpleNamespace(
        run_id=uuid4(),
        data_revision=revision,
        data_acquisitions=(
            baseline_authority.left_acquisition,
            baseline_authority.right_acquisition,
        ),
    )

    prepared = service._clean_revision(  # type: ignore[arg-type]
        context,
        step_key="cleaning_data",
        attempt=SimpleNamespace(),
        lease=SimpleNamespace(),
    )

    assert prepared.publications == ()
    assert checkpoint_queries == [(context.run_id, "cleaning_data")]
    assert len(admitted_crossmatches) == len(returned_authorities) == 1
    assert admitted_crossmatches[0] is returned_authorities[0].crossmatch_result
    assert baseline_with_documents.authority.document_observations == (
        "frozen-old-observation",
    )
    assert returned_authorities[0].document_observations == ()
