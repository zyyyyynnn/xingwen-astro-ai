"""Selective data-side execution for one confirmed RevisionPlan."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal
from uuid import UUID

from app.schemas.crossmatch import (
    CrossmatchRuleSet,
    CrossmatchSourceInput,
    EntityAliasCatalog,
    CrossmatchSourcePolicy,
    compute_crossmatch_source_input_hash,
)
from app.schemas.data_artifacts import (
    CrossmatchDataArtifactAuthority,
    DataArtifactBuildInput,
    DataArtifactBuildResult,
    MappingRuleSet,
    SourceTableDataArtifactAuthority,
    UnitConversionCatalog,
    compute_data_artifact_input_hash,
    compute_data_artifact_public_payload_hash,
)
from app.schemas.enums import SourceMode
from services.data_pipeline.data_artifacts import (
    build_data_artifact_candidates,
    readmit_data_artifact_candidates,
)


DataArtifactKind = Literal["dataset", "field_dictionary", "source_collection"]
RevisionDecision = Literal["recompute", "reuse"]
RevisionDisposition = Literal["recompute", "reuse"]
RevisionStage = Literal["source", "crossmatch", "mapping_unit", "quality"]
_KINDS: tuple[DataArtifactKind, ...] = (
    "dataset",
    "field_dictionary",
    "source_collection",
)


class DataRevisionErrorCode(StrEnum):
    baseline_stale = "REVISION_DATA_BASELINE_STALE"
    input_not_replayable = "REVISION_DATA_INPUT_NOT_REPLAYABLE"
    replan_required = "REVISION_DATA_REPLAN_REQUIRED"
    recompute_failed = "REVISION_DATA_RECOMPUTE_FAILED"


class DataRevisionError(ValueError):
    def __init__(self, code: DataRevisionErrorCode, detail: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {detail}")


@dataclass(frozen=True, slots=True)
class DataRevisionArtifactBaseline:
    artifact_kind: DataArtifactKind
    artifact_id: UUID
    baseline_version_id: UUID
    version_number: int
    decision: RevisionDecision
    step_key: str | None
    candidate_content_hash: str


@dataclass(frozen=True, slots=True)
class DataRevisionPublicationTarget:
    artifact_kind: DataArtifactKind
    artifact_id: UUID
    baseline_version_id: UUID
    supersedes_version_id: UUID
    candidate_id: str
    candidate_content_hash: str


@dataclass(frozen=True, slots=True)
class DataRevisionExecutionInput:
    plan_hash: str
    baselines: tuple[DataRevisionArtifactBaseline, ...]
    baseline_input: DataArtifactBuildInput
    baseline_result: DataArtifactBuildResult | None
    baseline_quality_rule_set_content_hash: str | None
    current_mapping_rule_set: MappingRuleSet
    current_conversion_catalog: UnitConversionCatalog
    current_crossmatch_rule_set: CrossmatchRuleSet
    current_alias_catalog: EntityAliasCatalog
    current_source_policy: CrossmatchSourcePolicy
    current_quality_rule_set_content_hash: str
    baseline_source_mode: SourceMode = SourceMode.live
    acquisition_recompute_authorized: bool = False
    acquire_sources: (
        Callable[[], tuple[CrossmatchSourceInput, CrossmatchSourceInput]] | None
    ) = None
    align_crossmatch_authority: (
        Callable[
            [CrossmatchSourceInput, CrossmatchSourceInput],
            CrossmatchDataArtifactAuthority,
        ]
        | None
    ) = None
    acquire_source_table_input: Callable[[], DataArtifactBuildInput] | None = None


@dataclass(frozen=True, slots=True)
class DataRevisionExecutionResult:
    disposition: RevisionDisposition
    required_stages: tuple[RevisionStage, ...]
    data_input: DataArtifactBuildInput | None
    build_result: DataArtifactBuildResult | None
    publication_targets: tuple[DataRevisionPublicationTarget, ...]


def execute_data_revision(
    execution: DataRevisionExecutionInput,
) -> DataRevisionExecutionResult:
    """Reuse valid upstream facts and rebuild one complete data bundle."""

    baselines = _validate_baselines(execution)
    decisions = {item.decision for item in baselines.values()}
    if decisions == {"reuse"}:
        try:
            baseline_result = _validate_baseline_payload(execution, baselines)
            _readmit_quality_baseline(execution.baseline_input, baseline_result)
            _validate_current_reuse_compatibility(execution)
        except DataRevisionError as exc:
            raise DataRevisionError(
                DataRevisionErrorCode.replan_required,
                "the frozen data bundle is not compatible with current reuse policy",
            ) from exc
        return DataRevisionExecutionResult("reuse", (), None, None, ())
    if decisions != {"recompute"}:
        raise DataRevisionError(
            DataRevisionErrorCode.replan_required,
            "the data bundle has mixed reuse and recompute decisions",
        )

    baseline_input = execution.baseline_input
    authority = baseline_input.authority
    stages: list[RevisionStage] = []

    if execution.acquisition_recompute_authorized:
        if isinstance(authority, SourceTableDataArtifactAuthority):
            if execution.acquire_source_table_input is None:
                raise DataRevisionError(
                    DataRevisionErrorCode.replan_required,
                    "authorized SourceTable acquisition has no scientific owner operation",
                )
            try:
                data_input = execution.acquire_source_table_input()
                if (
                    not isinstance(
                        data_input.authority, SourceTableDataArtifactAuthority
                    )
                    or data_input.manifest_pins != baseline_input.manifest_pins
                    or data_input.requested_fields != baseline_input.requested_fields
                    or data_input.mapping_rule_set
                    != execution.current_mapping_rule_set
                    or data_input.conversion_catalog
                    != execution.current_conversion_catalog
                    or data_input.quality_constraints_reference
                    != baseline_input.quality_constraints_reference
                ):
                    raise DataRevisionError(
                        DataRevisionErrorCode.recompute_failed,
                        "the scientific owner returned an incompatible SourceTable input",
                    )
                build_result = build_data_artifact_candidates(data_input)
            except DataRevisionError:
                raise
            except Exception as exc:
                raise DataRevisionError(
                    DataRevisionErrorCode.recompute_failed,
                    "the authorized SourceTable acquisition could not rebuild data artifacts",
                ) from exc
            targets = data_revision_publication_targets(
                baselines.values(), build_result
            )
            return DataRevisionExecutionResult(
                "recompute",
                ("source", "mapping_unit", "quality"),
                data_input,
                build_result,
                targets,
            )
        if not isinstance(authority, CrossmatchDataArtifactAuthority):
            raise DataRevisionError(
                DataRevisionErrorCode.replan_required,
                "source acquisition remains owned by the scientific producer",
            )
        if execution.acquire_sources is None:
            raise DataRevisionError(
                DataRevisionErrorCode.replan_required,
                "authorized acquisition recompute has no governed source operation",
            )
        left, right = execution.acquire_sources()
        stages.append("source")
    elif isinstance(authority, CrossmatchDataArtifactAuthority):
        left, right = authority.left_acquisition, authority.right_acquisition
    else:
        left = right = None

    crossmatch_changed = False
    if isinstance(authority, CrossmatchDataArtifactAuthority):
        context = authority.crossmatch_result.admission_context
        source_identity_changed = (
            execution.acquisition_recompute_authorized
            and _crossmatch_source_input_hash(
                baseline_input=baseline_input,
                left=left,
                right=right,
                rule_set=execution.current_crossmatch_rule_set,
                alias_catalog=execution.current_alias_catalog,
                source_policy=execution.current_source_policy,
            )
            != context.source_input_hash
        )
        crossmatch_changed = source_identity_changed or (
            context.rule_set != execution.current_crossmatch_rule_set
            or context.alias_catalog != execution.current_alias_catalog
            or context.source_policy != execution.current_source_policy
        )

    if crossmatch_changed:
        if (
            left is None
            or right is None
            or execution.align_crossmatch_authority is None
        ):
            raise DataRevisionError(
                DataRevisionErrorCode.replan_required,
                "Crossmatch recompute requires the current workflow repair authority",
            )
        authority = execution.align_crossmatch_authority(left, right)
        if authority.left_acquisition != left or authority.right_acquisition != right:
            raise DataRevisionError(
                DataRevisionErrorCode.recompute_failed,
                "the workflow Crossmatch authority returned different acquisitions",
            )
        stages.append("crossmatch")

    try:
        mapping_changed = (
            baseline_input.mapping_rule_set != execution.current_mapping_rule_set
            or baseline_input.conversion_catalog
            != execution.current_conversion_catalog
        )
        quality_changed = (
            execution.baseline_quality_rule_set_content_hash
            != execution.current_quality_rule_set_content_hash
        )
        if isinstance(authority, SourceTableDataArtifactAuthority) and mapping_changed:
            raise DataRevisionError(
                DataRevisionErrorCode.replan_required,
                "SourceTable mapping/unit recompute is not supported by its persisted authority",
            )
        if (
            execution.acquisition_recompute_authorized
            or crossmatch_changed
            or mapping_changed
        ):
            data_input = _rebuild_input(
                baseline_input,
                authority=authority,
                mapping_rule_set=execution.current_mapping_rule_set,
                conversion_catalog=execution.current_conversion_catalog,
            )
            build_result = build_data_artifact_candidates(data_input)
            stages.extend(("mapping_unit", "quality"))
        elif quality_changed:
            data_input = baseline_input
            try:
                baseline_result = _validate_baseline_payload(execution, baselines)
                build_result = _readmit_quality_baseline(
                    baseline_input,
                    baseline_result,
                )
                stages.append("quality")
            except DataRevisionError:
                if {item.step_key for item in baselines.values()} != {
                    "cleaning_data"
                }:
                    raise DataRevisionError(
                        DataRevisionErrorCode.replan_required,
                        "candidate reuse failed without an authorized complete rebuild",
                    )
                build_result = build_data_artifact_candidates(data_input)
                stages.extend(("mapping_unit", "quality"))
        else:
            raise DataRevisionError(
                DataRevisionErrorCode.replan_required,
                "affected Feedback has no supported structured data mutation",
            )
    except DataRevisionError:
        raise
    except Exception as exc:
        raise DataRevisionError(
            DataRevisionErrorCode.recompute_failed,
            "the authorized data recomputation did not produce a valid bundle",
        ) from exc

    targets = data_revision_publication_targets(baselines.values(), build_result)
    return DataRevisionExecutionResult(
        "recompute",
        tuple(stages),
        data_input,
        build_result,
        targets,
    )


def data_revision_publication_targets(
    baselines: Iterable[DataRevisionArtifactBaseline],
    build_result: DataArtifactBuildResult,
) -> tuple[DataRevisionPublicationTarget, ...]:
    """Bind complete candidate output to each artifact's own frozen baseline."""

    baseline_by_kind = {
        item.artifact_kind: item
        for item in baselines
    }
    if set(baseline_by_kind) != set(_KINDS) or any(
        item.decision != "recompute" for item in baseline_by_kind.values()
    ):
        raise DataRevisionError(
            DataRevisionErrorCode.replan_required,
            "publication requires three recompute decisions from one frozen data bundle",
        )
    candidates = {
        "dataset": build_result.dataset,
        "field_dictionary": build_result.field_dictionary,
        "source_collection": build_result.source_collection,
    }
    return tuple(
        DataRevisionPublicationTarget(
            artifact_kind=kind,
            artifact_id=baseline_by_kind[kind].artifact_id,
            baseline_version_id=baseline_by_kind[kind].baseline_version_id,
            supersedes_version_id=baseline_by_kind[kind].baseline_version_id,
            candidate_id=candidates[kind].candidate_id,
            candidate_content_hash=compute_data_artifact_public_payload_hash(
                candidates[kind]
            ),
        )
        for kind in _KINDS
    )


def _validate_baselines(
    execution: DataRevisionExecutionInput,
) -> dict[DataArtifactKind, DataRevisionArtifactBaseline]:
    by_kind = {item.artifact_kind: item for item in execution.baselines}
    if len(by_kind) != len(execution.baselines) or set(by_kind) != set(_KINDS):
        raise DataRevisionError(
            DataRevisionErrorCode.input_not_replayable,
            "the frozen data bundle is not an exact three-artifact set",
        )
    for item in by_kind.values():
        if item.version_number < 1 or (
            item.decision == "recompute"
        ) != (item.step_key is not None):
            raise DataRevisionError(
                DataRevisionErrorCode.input_not_replayable,
                "a frozen data decision has an invalid shape",
            )
    return by_kind


def _validate_baseline_payload(
    execution: DataRevisionExecutionInput,
    baselines: dict[DataArtifactKind, DataRevisionArtifactBaseline],
) -> DataArtifactBuildResult:
    try:
        replay_input = DataArtifactBuildInput.model_validate_json(
            execution.baseline_input.model_dump_json()
        )
        replayed = DataArtifactBuildResult.model_validate_json(
            execution.baseline_result.model_dump_json()
        )
    except Exception as exc:
        raise DataRevisionError(
            DataRevisionErrorCode.input_not_replayable,
            "the frozen build input or candidate bundle is not typed and self-validating",
        ) from exc
    if replayed.input_hash != replay_input.input_hash:
        raise DataRevisionError(
            DataRevisionErrorCode.input_not_replayable,
            "the frozen candidate bundle does not bind the replay input_hash",
        )
    candidates = {
        "dataset": replayed.dataset,
        "field_dictionary": replayed.field_dictionary,
        "source_collection": replayed.source_collection,
    }
    if any(
        baselines[kind].candidate_content_hash
        != compute_data_artifact_public_payload_hash(candidates[kind])
        for kind in _KINDS
    ):
        raise DataRevisionError(
            DataRevisionErrorCode.input_not_replayable,
            "a frozen ArtifactVersion content hash differs from the replayed candidate",
        )
    return replayed


def _readmit_quality_baseline(
    input_value: DataArtifactBuildInput,
    result: DataArtifactBuildResult,
) -> DataArtifactBuildResult:
    try:
        return readmit_data_artifact_candidates(input_value, result)
    except Exception as exc:
        raise DataRevisionError(
            DataRevisionErrorCode.input_not_replayable,
            "quality-only execution cannot exactly rederive the frozen data bundle",
        ) from exc


def _validate_current_reuse_compatibility(
    execution: DataRevisionExecutionInput,
) -> None:
    baseline = execution.baseline_input
    incompatible = (
        baseline.mapping_rule_set != execution.current_mapping_rule_set
        or baseline.conversion_catalog != execution.current_conversion_catalog
        or execution.baseline_quality_rule_set_content_hash
        != execution.current_quality_rule_set_content_hash
    )
    authority = baseline.authority
    if isinstance(authority, CrossmatchDataArtifactAuthority):
        context = authority.crossmatch_result.admission_context
        incompatible = incompatible or (
            context.rule_set != execution.current_crossmatch_rule_set
            or context.alias_catalog != execution.current_alias_catalog
            or context.source_policy != execution.current_source_policy
        )
    if incompatible:
        raise DataRevisionError(
            DataRevisionErrorCode.input_not_replayable,
            "the frozen data bundle does not satisfy current reuse policy",
        )


def _crossmatch_source_input_hash(
    *,
    baseline_input: DataArtifactBuildInput,
    left: CrossmatchSourceInput,
    right: CrossmatchSourceInput,
    rule_set: CrossmatchRuleSet,
    alias_catalog: EntityAliasCatalog,
    source_policy: CrossmatchSourcePolicy,
) -> str:
    pins = baseline_input.manifest_pins
    payload = {
        "case_manifest_id": pins.case_manifest_id,
        "case_manifest_version": pins.case_manifest_version,
        "case_manifest_content_hash": pins.case_manifest_content_hash,
        "field_manifest_id": pins.field_manifest_id,
        "field_manifest_version": pins.field_manifest_version,
        "field_manifest_content_hash": pins.field_manifest_content_hash,
        "rule_set": rule_set.model_dump(mode="json"),
        "alias_catalog": alias_catalog.model_dump(mode="json"),
        "source_policy": source_policy.model_dump(mode="json"),
        "left": left.model_dump(mode="json"),
        "right": right.model_dump(mode="json"),
    }
    return compute_crossmatch_source_input_hash(payload)


def _rebuild_input(
    baseline: DataArtifactBuildInput,
    *,
    authority: object,
    mapping_rule_set: MappingRuleSet,
    conversion_catalog: UnitConversionCatalog,
) -> DataArtifactBuildInput:
    payload = {
        "manifest_pins": baseline.manifest_pins,
        "requested_fields": baseline.requested_fields,
        "authority": authority,
        "mapping_rule_set": mapping_rule_set,
        "conversion_catalog": conversion_catalog,
        "producer_version": mapping_rule_set.producer_version,
        "quality_constraints_reference": baseline.quality_constraints_reference,
    }
    unhashed = DataArtifactBuildInput.model_construct(
        **payload,
        input_hash="sha256:" + "0" * 64,
    )
    payload["input_hash"] = compute_data_artifact_input_hash(unhashed)
    return DataArtifactBuildInput.model_validate(payload)


__all__ = [
    "DataRevisionArtifactBaseline",
    "DataRevisionError",
    "DataRevisionErrorCode",
    "DataRevisionExecutionInput",
    "DataRevisionExecutionResult",
    "DataRevisionPublicationTarget",
    "data_revision_publication_targets",
    "execute_data_revision",
]
