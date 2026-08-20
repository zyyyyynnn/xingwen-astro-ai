"""Data acquisition and cleaning step services for Research Runs."""

from __future__ import annotations

from typing import Any

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    RepairCheckpointContext,
    RepairDefect,
    RepairEvidenceFact,
    RepairOutcome,
    RepairRuleSetReference,
)
from app.schemas.crossmatch import (
    AdjudicationDecision,
    ConflictGroup,
    CrossmatchCondition,
    CrossmatchInput,
    CrossmatchResult,
    ManualReviewDecision,
    MatchDecision,
    PairedMatch,
    ReviewerKind,
    compute_crossmatch_input_hash,
    compute_crossmatch_source_input_hash,
)
from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    ManifestPins,
    compute_data_artifact_input_hash,
)
from app.schemas.data_quality import (
    DataQualityEvaluationInput,
    DataQualityEvaluationResult,
    compute_data_quality_input_hash,
)
from app.schemas.manifest import ManifestBundle
from app.security import canonical_request_hash
from app.workflow.publisher import admit_artifact_candidate
from app.workflow.step_publication import (
    PreparedStep,
    RunStepContext,
    StepPublicationFactory,
)
from app.workflow.store import (
    AttemptHandle,
    LeaseGrant,
    PersistentWorkflowStore,
    WorkflowCheckpointRequested,
)
from services.data_pipeline.crossmatch import align_cross_source_records
from services.data_pipeline.crossmatch.policy import (
    load_crossmatch_rule_set,
    load_crossmatch_source_policy,
    load_entity_alias_catalog,
)
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.data_artifacts.admission import (
    validate_data_artifact_domain,
    validate_data_artifact_evidence,
)
from services.data_pipeline.data_artifacts.policy import (
    load_mapping_rule_set,
    load_unit_conversion_catalog,
)
from services.data_pipeline.data_quality import (
    admit_data_artifact_quality,
    build_data_quality_publication_validator,
    evaluate_data_quality,
)
from services.data_pipeline.data_quality.policy import load_frozen_quality_rule_set
from services.data_pipeline.live_acquisition import acquire_case_sources


class DataStepService:
    """Fetch and clean the frozen case data closure for one confirmed Contract."""

    def __init__(
        self,
        *,
        manifests: ManifestBundle,
        publications: StepPublicationFactory,
        store: PersistentWorkflowStore,
    ) -> None:
        self._manifests = manifests
        self._publications = publications
        self._store = store

    def fetch(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> PreparedStep:
        input_hash = canonical_request_hash(
            {
                "case_manifest": self._manifests.case_manifest.content_hash,
                "field_manifest": self._manifests.field_manifest.content_hash,
                "contract": context.contract.model_dump(mode="json"),
            }
        )
        execution = self._publications.start_producer(
            context,
            step_key=step_key,
            operation_key="data_acquisition",
            producer_type="pipeline",
            producer_name="contract-data-acquisition",
            producer_version=self._manifests.case_manifest.manifest_version,
            input_hash=input_hash,
            parameters={},
            attempt=attempt,
            lease=lease,
        )
        try:
            acquisitions = acquire_case_sources(self._manifests, context.contract)
        except Exception:
            self._publications.finish_producer(
                execution.id, status="failed", error_code="DATA_ACQUISITION_FAILED"
            )
            raise
        context.data_acquisitions = acquisitions
        self._publications.finish_producer(
            execution.id,
            status="completed",
            output_hash=canonical_request_hash(
                [item.model_dump(mode="json") for item in acquisitions]
            ),
        )
        return PreparedStep((), activity_result_summary="已按研究协议获取所需数据材料")

    def clean(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> PreparedStep:
        acquisitions = context.data_acquisitions
        if acquisitions is None:
            raise ValueError("fetching_data must complete before cleaning_data")
        left, right = acquisitions
        rules = load_crossmatch_rule_set()
        crossmatch_payload: dict[str, Any] = {
            "case_manifest_id": self._manifests.case_manifest.case_id,
            "case_manifest_version": self._manifests.case_manifest.manifest_version,
            "case_manifest_content_hash": self._manifests.case_manifest.content_hash,
            "field_manifest_id": self._manifests.field_manifest.manifest_id,
            "field_manifest_version": self._manifests.field_manifest.manifest_version,
            "field_manifest_content_hash": self._manifests.field_manifest.content_hash,
            "rule_set": rules.model_dump(mode="json"),
            "alias_catalog": load_entity_alias_catalog().model_dump(mode="json"),
            "source_policy": load_crossmatch_source_policy().model_dump(mode="json"),
            "left": left.model_dump(mode="json"),
            "right": right.model_dump(mode="json"),
            "manual_review_decisions": (),
        }
        crossmatch_payload["source_input_hash"] = compute_crossmatch_source_input_hash(
            crossmatch_payload
        )
        crossmatch_payload["input_hash"] = compute_crossmatch_input_hash(
            crossmatch_payload
        )
        crossmatch_input = CrossmatchInput.model_validate(crossmatch_payload)
        crossmatch = align_cross_source_records(crossmatch_input)
        defects = _repair_defects(crossmatch)
        repair_state = self._store.repair_checkpoint_decision(
            context.run_id, step_key=step_key
        )
        if defects and repair_state is None:
            repair_context = RepairCheckpointContext(
                rule_set=RepairRuleSetReference(
                    rule_set_id=rules.rule_set_id,
                    rule_set_version=rules.version,
                    rule_set_content_hash=rules.content_hash,
                ),
                source_input_hash=crossmatch_input.source_input_hash,
                before_output_hash=crossmatch.output_hash,
                defects=defects,
            )
            self._store.request_checkpoint(
                context.run_id,
                step_key=step_key,
                token=lease.token,
                generation=lease.generation,
                expected_status=attempt.run_status,
                expected_revision=attempt.run_revision,
                attempt_id=attempt.attempt_id,
                question=(
                    f"发现 {len(defects)} 项跨来源科学身份冲突，请逐项核对证据后决定。"
                ),
                options=("accepted", "rejected", "keep_unresolved"),
                kind="scientific_repair",
                repair_context=repair_context,
            )
            raise WorkflowCheckpointRequested()
        if repair_state is not None:
            _validate_repair_checkpoint(
                repair_state.context,
                defects=defects,
                rules=rules,
                source_input_hash=crossmatch_input.source_input_hash,
                before_output_hash=crossmatch.output_hash,
            )
            crossmatch_payload["manual_review_decisions"] = tuple(
                _manual_review_decision(
                    decision,
                    defect=next(
                        item for item in defects if item.defect_id == decision.defect_id
                    ),
                    checkpoint_id=str(repair_state.checkpoint_id),
                    decided_at=repair_state.decided_at,
                    source_input_hash=crossmatch_input.source_input_hash,
                    rules=rules,
                )
                for decision in repair_state.decisions
            )
            crossmatch_payload["input_hash"] = compute_crossmatch_input_hash(
                crossmatch_payload
            )
            crossmatch_input = CrossmatchInput.model_validate(crossmatch_payload)
            crossmatch = align_cross_source_records(crossmatch_input)
        mapping = load_mapping_rule_set()
        conversion = load_unit_conversion_catalog()
        pins = ManifestPins(
            case_manifest_id=crossmatch.case_manifest_id,
            case_manifest_version=crossmatch.case_manifest_version,
            case_manifest_content_hash=crossmatch.case_manifest_content_hash,
            field_manifest_id=crossmatch.field_manifest_id,
            field_manifest_version=crossmatch.field_manifest_version,
            field_manifest_content_hash=crossmatch.field_manifest_content_hash,
        )
        data_payload: dict[str, Any] = {
            "manifest_pins": pins,
            "requested_fields": context.contract.requested_fields,
            "left_acquisition": left,
            "right_acquisition": right,
            "crossmatch_result": crossmatch,
            "mapping_rule_set": mapping,
            "conversion_catalog": conversion,
            "producer_version": mapping.producer_version,
            "quality_constraints_reference": "research_contract.quality_constraints",
        }
        unhashed = DataArtifactBuildInput.model_construct(
            **data_payload,
            input_hash="sha256:" + "0" * 64,
        )
        data_payload["input_hash"] = compute_data_artifact_input_hash(unhashed)
        data_input = DataArtifactBuildInput.model_validate(data_payload)
        producer_version = mapping.producer_version
        build_executions = {
            kind: self._publications.start_producer(
                context,
                step_key=step_key,
                operation_key=f"data_artifact:{kind}",
                producer_type="algorithm",
                producer_name=f"data-artifact-{kind}",
                producer_version=producer_version,
                input_hash=data_input.input_hash,
                parameters={},
                attempt=attempt,
                lease=lease,
            )
            for kind in ("dataset", "field_dictionary", "source_collection")
        }
        build_executions_closed = False
        try:
            build_result = build_data_artifact_candidates(data_input)
            quality_payload: dict[str, Any] = {
                "data_artifact_input": data_input,
                "dataset_candidate": build_result.dataset,
                "field_dictionary_candidate": build_result.field_dictionary,
                "source_collection_candidate": build_result.source_collection,
                "research_contract": context.contract,
                "quality_rule_set": load_frozen_quality_rule_set(),
            }
            quality_unhashed = DataQualityEvaluationInput.model_construct(
                **quality_payload,
                input_hash="sha256:" + "0" * 64,
            )
            quality_payload["input_hash"] = compute_data_quality_input_hash(
                quality_unhashed
            )
            quality_input = DataQualityEvaluationInput.model_validate(quality_payload)
            quality_result = evaluate_data_quality(quality_input)
            if not isinstance(quality_result, DataQualityEvaluationResult):
                raise ValueError("实时数据未通过研究协议的数据质量约束")
            quality = admit_data_artifact_quality(
                build_result=build_result,
                evaluation_input=quality_input,
                evaluation_result=quality_result,
            )
            if repair_state is not None:
                outcome = _repair_outcome(
                    repair_state=repair_state,
                    before_defects=defects,
                    crossmatch=crossmatch,
                    quality_result=quality_result,
                )
                self._store.complete_repair_checkpoint(
                    context.run_id,
                    step_key=step_key,
                    checkpoint_id=repair_state.checkpoint_id,
                    outcome=outcome,
                    token=lease.token,
                    generation=lease.generation,
                    expected_status=attempt.run_status,
                    expected_revision=attempt.run_revision,
                )
                if outcome.status == "false_repair":
                    for execution in build_executions.values():
                        self._publications.finish_producer(
                            execution.id,
                            status="rejected",
                            error_code="REPAIR_REVALIDATION_FAILED",
                        )
                    build_executions_closed = True
                    raise ValueError("人工修复决定未通过确定性重验证")
        except Exception:
            if not build_executions_closed:
                for execution in build_executions.values():
                    self._publications.finish_producer(
                        execution.id,
                        status="failed",
                        error_code="DATA_ARTIFACT_BUILD_FAILED",
                    )
            raise
        self._publications.ensure_source_snapshots(
            context, (left.snapshot, right.snapshot)
        )
        publications = []
        for kind, candidate in (
            ("dataset", build_result.dataset),
            ("field_dictionary", build_result.field_dictionary),
            ("source_collection", build_result.source_collection),
        ):
            source_bindings, evidence_bindings = self._publications.data_bindings(
                context,
                kind=kind,
                candidate=build_result.dataset,
            )
            admitted = admit_artifact_candidate(
                candidate,
                schema_version=candidate.schema_version,
                source_snapshot_ids=candidate.source_snapshot_ids,
                evidence_ids=candidate.evidence_ids,
                evidence_validator=validate_data_artifact_evidence,
                domain_validator=validate_data_artifact_domain,
                quality_validator=build_data_quality_publication_validator(
                    quality,
                    candidate_kind=kind,
                ),
                source_snapshot_bindings=source_bindings,
                evidence_bindings=evidence_bindings,
                data_provenance_candidate=(
                    None if kind == "dataset" else build_result.dataset
                ),
            )
            execution = build_executions[kind]
            self._publications.finish_producer(
                execution.id,
                status="completed",
                input_hash=candidate.input_hash,
                output_hash=admitted.content_hash,
            )
            publications.append(
                self._publications.publication(
                    context,
                    kind=kind,
                    candidate=admitted,
                    producer_execution_id=execution.id,
                )
            )
        context.data_result = build_result
        return PreparedStep(
            publications=tuple(publications),
            activity_result_summary=(
                "已完成研究数据对齐与质量校验，共输出 "
                f"{len(build_result.dataset.records)} 条规范化记录"
            ),
        )


def _repair_defects(crossmatch: CrossmatchResult) -> tuple[RepairDefect, ...]:
    defects: list[RepairDefect] = []
    evidence_by_id = {item.evidence_id: item for item in crossmatch.evidence}
    for record in crossmatch.records:
        if isinstance(record, ConflictGroup):
            conflict_code = record.conflict_code
        elif (
            isinstance(record, PairedMatch)
            and record.decision is MatchDecision.review_required
        ):
            conflict_code = "low_confidence_match"
        else:
            continue
        defects.append(
            RepairDefect(
                defect_id=f"repair-{record.logical_match_key[7:31]}",
                logical_match_key=record.logical_match_key,
                conflict_code=conflict_code,
                left_candidate_ids=tuple(sorted(record.left_candidate_ids)),
                right_candidate_ids=tuple(sorted(record.right_candidate_ids)),
                evidence=tuple(
                    RepairEvidenceFact(
                        evidence_id=item.evidence_id,
                        left_candidate_id=item.left_candidate_id,
                        right_candidate_id=item.right_candidate_id,
                        confidence=item.confidence,
                        summary="；".join(
                            _repair_condition_summary(condition)
                            for condition in item.conditions
                        ),
                    )
                    for item in sorted(
                        (evidence_by_id[value] for value in record.evidence_ids),
                        key=lambda value: value.evidence_id,
                    )
                ),
            )
        )
    return tuple(sorted(defects, key=lambda item: item.defect_id))


def _repair_condition_summary(condition: CrossmatchCondition) -> str:
    if condition.separation_arcsec is not None:
        return (
            f"角距离 {condition.separation_arcsec:.3f} 角秒；"
            f"自动接受阈值 {condition.strict_threshold_arcsec:.3f} 角秒；"
            f"人工复核阈值 {condition.manual_review_threshold_arcsec:.3f} 角秒"
        )
    labels = {
        "exact": "字段完全一致",
        "curated_alias": "命中受控别名",
        "contradicts": "字段值冲突",
    }
    operator = condition.operator.value
    label = labels.get(operator, "候选匹配条件")
    field = condition.field_id or "标识字段"
    return f"{field}：{condition.left_value} / {condition.right_value}（{label}）"


def _validate_repair_checkpoint(
    repair_context: RepairCheckpointContext,
    *,
    defects: tuple[RepairDefect, ...],
    rules: Any,
    source_input_hash: str,
    before_output_hash: str,
) -> None:
    if (
        repair_context.defects != defects
        or repair_context.source_input_hash != source_input_hash
        or repair_context.before_output_hash != before_output_hash
        or repair_context.rule_set.rule_set_id != rules.rule_set_id
        or repair_context.rule_set.rule_set_version != rules.version
        or repair_context.rule_set.rule_set_content_hash != rules.content_hash
    ):
        raise ValueError("科学修复检查点与当前不可变输入或 RuleSet 不一致")


def _manual_review_decision(
    decision: Any,
    *,
    defect: RepairDefect,
    checkpoint_id: str,
    decided_at: Any,
    source_input_hash: str,
    rules: Any,
) -> ManualReviewDecision:
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "decision_id": f"{checkpoint_id}:{defect.defect_id}",
        "logical_match_key": defect.logical_match_key,
        "adjudication": AdjudicationDecision(decision.action),
        "adjudicated_by": "workspace_user",
        "reviewer_kind": ReviewerKind.human,
        "adjudication_rule_or_actor": (f"{rules.rule_set_id}@{rules.version}"),
        "adjudicated_at": decided_at,
        "rationale": decision.rationale,
        "source_input_hash": source_input_hash,
        "rule_set_id": rules.rule_set_id,
        "rule_set_version": rules.version,
        "rule_set_content_hash": rules.content_hash,
        "left_candidate_ids": defect.left_candidate_ids,
        "right_candidate_ids": defect.right_candidate_ids,
        "evidence_ids": tuple(item.evidence_id for item in defect.evidence),
    }
    payload["content_hash"] = compute_canonical_payload_hash(
        {
            key: (
                value.isoformat().replace("+00:00", "Z")
                if key == "adjudicated_at"
                else value.value
                if hasattr(value, "value")
                else value
            )
            for key, value in payload.items()
        }
    )
    return ManualReviewDecision.model_validate(payload)


def _repair_outcome(
    *,
    repair_state: Any,
    before_defects: tuple[RepairDefect, ...],
    crossmatch: Any,
    quality_result: DataQualityEvaluationResult,
) -> RepairOutcome:
    remaining = {
        item.logical_match_key
        for item in crossmatch.records
        if isinstance(item, ConflictGroup)
        or (
            isinstance(item, PairedMatch)
            and item.decision is MatchDecision.review_required
        )
    }
    defects_by_id = {item.defect_id: item for item in before_defects}
    false_repair = False
    resolved: list[str] = []
    unresolved: list[str] = []
    for decision in repair_state.decisions:
        defect = defects_by_id[decision.defect_id]
        remains = defect.logical_match_key in remaining
        if remains:
            unresolved.append(defect.defect_id)
        else:
            resolved.append(defect.defect_id)
        if (decision.action == "keep_unresolved") != remains:
            false_repair = True
    after_evidence = sorted(
        {
            evidence_id
            for record in crossmatch.records
            for evidence_id in getattr(record, "evidence_ids", ())
        }
    )
    return RepairOutcome(
        after_output_hash=crossmatch.output_hash,
        quality_result_hash=quality_result.content_hash,
        before_evidence_ids=tuple(
            sorted(
                {
                    evidence_id
                    for defect in before_defects
                    for evidence_id in (item.evidence_id for item in defect.evidence)
                }
            )
        ),
        after_evidence_ids=tuple(after_evidence),
        resolved_defect_ids=tuple(sorted(resolved)),
        unresolved_defect_ids=tuple(sorted(unresolved)),
        status="false_repair" if false_repair else "revalidated",
    )


__all__ = ["DataStepService"]
