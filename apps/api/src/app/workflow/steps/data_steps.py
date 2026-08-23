"""Data acquisition and cleaning step services for Research Runs."""

from __future__ import annotations

import asyncio
from typing import Any

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ArtifactKind,
    RepairCheckpointContext,
    RepairCandidateCoordinate,
    RepairCandidateIdentity,
    RepairCandidateSummary,
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
    EntityCandidate,
    ManualReviewDecision,
    MatchDecision,
    PairedMatch,
    ReviewerKind,
    compute_crossmatch_input_hash,
    compute_crossmatch_source_input_hash,
)
from app.schemas.data_artifacts import (
    CrossmatchDataArtifactAuthority,
    DataArtifactBuildInput,
    ManifestPins,
    compute_data_artifact_input_hash,
)
from app.schemas.data_quality import DataQualityEvaluationResult
from app.schemas.manifest import ManifestBundle
from app.security import canonical_request_hash
from app.services.document_data_admission import (
    DocumentDataAdmissionBatch,
    DocumentDataAdmissionService,
)
from app.workflow.data_artifact_publication import (
    DataArtifactPublicationConfig,
    DataArtifactPublicationService,
)
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
from services.data_pipeline.data_artifacts.projection import (
    derive_document_snapshot_bindings,
)
from services.data_pipeline.data_artifacts.policy import (
    load_mapping_rule_set,
    load_unit_conversion_catalog,
)
from services.data_pipeline.live_acquisition import acquire_case_sources


class DataStepService:
    """Fetch and clean the frozen case data closure for one confirmed Contract."""

    def __init__(
        self,
        *,
        manifests: ManifestBundle,
        publications: StepPublicationFactory,
        store: PersistentWorkflowStore,
        document_admission: DocumentDataAdmissionService | None = None,
    ) -> None:
        self._manifests = manifests
        self._publications = publications
        self._store = store
        self._document_admission = document_admission
        self._data_artifacts = DataArtifactPublicationService(publications)

    def _admit_document_observations(
        self,
        context: RunStepContext,
        *,
        crossmatch: CrossmatchResult,
        attempt: AttemptHandle,
        lease: LeaseGrant,
        step_key: str,
    ) -> DocumentDataAdmissionBatch | None:
        """Run document-data admission inside cleaning_data when configured."""

        if self._document_admission is None:
            return None
        plan = asyncio.run(
            self._document_admission.prepare(
                project_id=context.project_id,
                run_id=context.run_id,
                contract=context.contract,
                crossmatch=crossmatch,
            )
        )
        if plan is None:
            return None
        execution = self._publications.start_producer(
            context,
            step_key=step_key,
            operation_key="data_artifact:document_observations",
            producer_type="algorithm",
            producer_name=plan.producer_name,
            producer_version=plan.producer_version,
            input_hash=plan.producer_input_hash,
            parameters=plan.producer_parameters,
            attempt=attempt,
            lease=lease,
        )
        try:
            batch = self._document_admission.execute(plan)
        except Exception as exc:
            error_code = getattr(exc, "code", "DOCUMENT_DATA_ADMISSION_FAILED")
            error_code = getattr(error_code, "value", error_code)
            self._publications.finish_producer(
                execution.id,
                status="failed",
                error_code=str(error_code),
            )
            raise
        self._publications.finish_producer(
            execution.id,
            status="completed",
            output_hash=batch.producer_output_hash,
        )
        return batch

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
        defects = _repair_defects(crossmatch, manifests=self._manifests)
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
        # Document observations enter the existing cleaning chain after
        # the frozen CrossmatchResult exists and before the Data Artifact
        # build input is created. This is a C-domain extension of
        # cleaning_data, never a new RunStep.
        document_batch = self._admit_document_observations(
            context,
            crossmatch=crossmatch,
            attempt=attempt,
            lease=lease,
            step_key=step_key,
        )
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
            "authority": CrossmatchDataArtifactAuthority(
                left_acquisition=left,
                right_acquisition=right,
                crossmatch_result=crossmatch,
                document_observations=(
                    document_batch.accepted if document_batch is not None else ()
                ),
            ),
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
        document_snapshot_bindings = derive_document_snapshot_bindings(data_input)
        publication_config = DataArtifactPublicationConfig(
            publish_kinds=(
                ArtifactKind.dataset,
                ArtifactKind.field_dictionary,
                ArtifactKind.source_collection,
            ),
            operation_key_prefix="data_artifact",
            producer_error_code="DATA_ARTIFACT_BUILD_FAILED",
            producer_version=mapping.producer_version,
            quality_failure_message="实时数据未通过研究协议的数据质量约束",
            snapshot_bindings_override=document_snapshot_bindings,
            source_snapshots=(left.snapshot, right.snapshot),
        )
        prepared = self._data_artifacts.prepare(
            context,
            step_key=step_key,
            attempt=attempt,
            lease=lease,
            data_input=data_input,
            config=publication_config,
        )
        build_executions_closed = False
        try:
            if repair_state is not None:
                outcome = _repair_outcome(
                    repair_state=repair_state,
                    before_defects=defects,
                    crossmatch=crossmatch,
                    quality_result=prepared.quality.evaluation_result,
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
                    for execution in prepared.executions.values():
                        self._publications.finish_producer(
                            execution.id,
                            status="rejected",
                            error_code="REPAIR_REVALIDATION_FAILED",
                        )
                    build_executions_closed = True
                    raise ValueError("人工修复决定未通过确定性重验证")
        except Exception:
            if not build_executions_closed:
                for execution in prepared.executions.values():
                    self._publications.finish_producer(
                        execution.id,
                        status="failed",
                        error_code="DATA_ARTIFACT_BUILD_FAILED",
                    )
            raise
        publications = self._data_artifacts.publish(
            context,
            prepared=prepared,
            config=publication_config,
        )
        return PreparedStep(
            publications=publications,
            activity_result_summary=(
                "已完成研究数据对齐与质量校验，共输出 "
                f"{len(prepared.build_result.dataset.rows)} 条规范化记录"
            ),
        )


def _repair_defects(
    crossmatch: CrossmatchResult, *, manifests: ManifestBundle
) -> tuple[RepairDefect, ...]:
    defects: list[RepairDefect] = []
    evidence_by_id = {item.evidence_id: item for item in crossmatch.evidence}
    candidates_by_id = {item.candidate_id: item for item in crossmatch.candidates}
    field_labels = {
        item.field_id: item.meaning_zh for item in manifests.field_manifest.fields
    }
    source_labels = {
        item.source_id: item.name for item in manifests.field_manifest.sources
    }
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
                left_candidates=tuple(
                    _repair_candidate_summary(
                        candidates_by_id[candidate_id],
                        field_labels=field_labels,
                        source_labels=source_labels,
                    )
                    for candidate_id in sorted(record.left_candidate_ids)
                ),
                right_candidates=tuple(
                    _repair_candidate_summary(
                        candidates_by_id[candidate_id],
                        field_labels=field_labels,
                        source_labels=source_labels,
                    )
                    for candidate_id in sorted(record.right_candidate_ids)
                ),
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


def _repair_candidate_summary(
    candidate: EntityCandidate,
    *,
    field_labels: dict[str, str],
    source_labels: dict[str, str],
) -> RepairCandidateSummary:
    entity_labels = {
        "host_star": "宿主恒星",
        "planet_candidate": "行星候选体",
        "planet_assertion": "行星记录",
    }
    coordinate = candidate.coordinate
    return RepairCandidateSummary(
        candidate_id=candidate.candidate_id,
        source_label=source_labels[candidate.source_record.source_id],
        entity_label=entity_labels[candidate.entity_level.value],
        identities=tuple(
            RepairCandidateIdentity(
                label=field_labels[item.field_id],
                value=item.normalized_value,
            )
            for item in candidate.identity_values
        ),
        coordinate=(
            RepairCandidateCoordinate(
                right_ascension_degrees=coordinate.right_ascension,
                declination_degrees=coordinate.declination,
            )
            if coordinate is not None
            else None
        ),
    )


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
        "left_candidate_ids": tuple(
            item.candidate_id for item in defect.left_candidates
        ),
        "right_candidate_ids": tuple(
            item.candidate_id for item in defect.right_candidates
        ),
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
