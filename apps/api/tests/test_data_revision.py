"""Selective data-revision domain execution through one stable interface."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from app.schemas.crossmatch import CrossmatchRuleSet, compute_crossmatch_content_hash
from app.schemas.data_artifacts import (
    compute_data_artifact_content_hash,
    compute_data_artifact_public_payload_hash,
)
from data_artifact_test_support import build_input
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.data_artifacts import projection as projection_module
from services.data_pipeline.revision import (
    DataRevisionArtifactBaseline,
    DataRevisionError,
    DataRevisionExecutionInput,
    execute_data_revision,
)


HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


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
            acquisition_recompute_authorized=scenario == "source",
            acquire_sources=acquire_sources,
        ),
        acquisition_calls,
    )


@pytest.mark.parametrize(
    ("scenario", "expected_stages"),
    (
        ("source", ("source", "crossmatch", "mapping_unit", "quality")),
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

    assert first.executed_stages == expected_stages
    assert second.executed_stages == expected_stages
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
