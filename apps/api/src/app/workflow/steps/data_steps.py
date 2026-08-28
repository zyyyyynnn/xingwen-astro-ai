"""Data acquisition and cleaning step services for Research Runs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any

from app.schemas.core import (
    ArtifactKind,
    RepairCheckpointContext,
    RepairDefect,
    RepairOutcome,
    RepairRuleSetReference,
)
from app.schemas.crossmatch import (
    CrossmatchInput,
    CrossmatchResult,
    CrossmatchSourceInput,
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
from app.services.data_artifact_build_inputs import DataArtifactBuildInputRepository
from app.workflow.data_artifact_publication import (
    DataArtifactPublicationConfig,
    DataArtifactPublicationService,
)
from app.workflow.document_parse_execution import DocumentParseExecutionService
from app.workflow.step_publication import (
    PreparedStep,
    RunStepContext,
    StepPublicationFactory,
)
from app.workflow.store import (
    AttemptHandle,
    LeaseGrant,
    PersistentWorkflowStore,
    RepairCheckpointDecisionState,
    WorkflowCheckpointRequested,
)
from services.data_pipeline.crossmatch import align_cross_source_records
from services.data_pipeline.crossmatch.policy import (
    load_crossmatch_rule_set,
    load_crossmatch_source_policy,
    load_entity_alias_catalog,
)
from services.data_pipeline.crossmatch.repair import (
    assess_repair_resolution,
    build_repair_manual_review_decision,
    derive_repair_defects,
    validate_repair_checkpoint,
)
from services.data_pipeline.data_artifacts.projection import (
    derive_document_snapshot_bindings,
)
from services.data_pipeline.data_artifacts.policy import (
    load_mapping_rule_set,
    load_unit_conversion_catalog,
)
from services.data_pipeline.live_acquisition import acquire_case_sources
from services.data_pipeline.revision import execute_data_revision


@dataclass(frozen=True, slots=True)
class _AlignmentOutcome:
    crossmatch: CrossmatchResult
    defects: tuple[RepairDefect, ...]
    repair_state: RepairCheckpointDecisionState | None


class DataStepService:
    """Fetch and clean the frozen case data closure for one confirmed Contract."""

    def __init__(
        self,
        *,
        manifests: ManifestBundle,
        publications: StepPublicationFactory,
        store: PersistentWorkflowStore,
        build_inputs: DataArtifactBuildInputRepository,
        document_admission: DocumentDataAdmissionService | None = None,
        document_parse_execution: DocumentParseExecutionService | None = None,
    ) -> None:
        self._manifests = manifests
        self._publications = publications
        self._store = store
        self._document_admission = document_admission
        self._document_parse_execution = document_parse_execution
        self._data_artifacts = DataArtifactPublicationService(
            publications,
            build_inputs,
        )

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
        if self._document_parse_execution is not None:
            self._document_parse_execution.parse_bound_inputs(
                context,
                step_key=step_key,
                attempt=attempt,
                lease=lease,
            )
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

    def _align_with_current_repair_authority(
        self,
        context: RunStepContext,
        *,
        left: CrossmatchSourceInput,
        right: CrossmatchSourceInput,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> _AlignmentOutcome:
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
        defects = derive_repair_defects(crossmatch, manifests=self._manifests)
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
            validate_repair_checkpoint(
                repair_state.context,
                defects=defects,
                rules=rules,
                source_input_hash=crossmatch_input.source_input_hash,
                before_output_hash=crossmatch.output_hash,
            )
            crossmatch_payload["manual_review_decisions"] = tuple(
                build_repair_manual_review_decision(
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
        return _AlignmentOutcome(crossmatch, defects, repair_state)

    def _complete_alignment_repair(
        self,
        context: RunStepContext,
        *,
        alignment: _AlignmentOutcome,
        quality_result: DataQualityEvaluationResult,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> RepairOutcome | None:
        repair_state = alignment.repair_state
        if repair_state is None:
            return None
        outcome = _repair_outcome(
            repair_state=repair_state,
            before_defects=alignment.defects,
            crossmatch=alignment.crossmatch,
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
        return outcome

    def clean(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> PreparedStep:
        if context.data_revision is not None:
            return self._clean_revision(
                context,
                step_key=step_key,
                attempt=attempt,
                lease=lease,
            )
        acquisitions = context.data_acquisitions
        if acquisitions is None:
            raise ValueError("fetching_data must complete before cleaning_data")
        left, right = acquisitions
        alignment = self._align_with_current_repair_authority(
            context,
            left=left,
            right=right,
            step_key=step_key,
            attempt=attempt,
            lease=lease,
        )
        crossmatch = alignment.crossmatch
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
            outcome = self._complete_alignment_repair(
                context,
                alignment=alignment,
                quality_result=prepared.quality.evaluation_result,
                step_key=step_key,
                attempt=attempt,
                lease=lease,
            )
            if outcome is not None and outcome.status == "false_repair":
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

    def _clean_revision(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> PreparedStep:
        revision = context.data_revision
        if revision is None:
            raise ValueError("data revision context is required")

        def acquire_sources():
            if context.data_acquisitions is None:
                context.data_acquisitions = acquire_case_sources(
                    self._manifests,
                    context.contract,
                )
            return context.data_acquisitions

        alignment: _AlignmentOutcome | None = None

        def align_crossmatch_authority(
            left: CrossmatchSourceInput,
            right: CrossmatchSourceInput,
        ) -> CrossmatchDataArtifactAuthority:
            nonlocal alignment
            alignment = self._align_with_current_repair_authority(
                context,
                left=left,
                right=right,
                step_key=step_key,
                attempt=attempt,
                lease=lease,
            )
            document_batch = self._admit_document_observations(
                context,
                crossmatch=alignment.crossmatch,
                attempt=attempt,
                lease=lease,
                step_key=step_key,
            )
            return CrossmatchDataArtifactAuthority(
                left_acquisition=left,
                right_acquisition=right,
                crossmatch_result=alignment.crossmatch,
                document_observations=(
                    document_batch.accepted if document_batch is not None else ()
                ),
            )

        result = execute_data_revision(
            replace(
                revision,
                acquire_sources=acquire_sources,
                align_crossmatch_authority=align_crossmatch_authority,
            )
        )
        if result.disposition == "reuse":
            return PreparedStep((), "已复用修订计划冻结的数据版本。")
        if result.data_input is None or result.build_result is None:
            raise ValueError("data revision recompute returned no complete bundle")
        if result.resulting_source_mode is None:
            raise ValueError("data revision returned no resulting source provenance")
        authority = result.data_input.authority
        if not isinstance(authority, CrossmatchDataArtifactAuthority):
            raise ValueError("cleaning_data revision requires Crossmatch authority")
        publication_config = DataArtifactPublicationConfig(
            publish_kinds=(
                ArtifactKind.dataset,
                ArtifactKind.field_dictionary,
                ArtifactKind.source_collection,
            ),
            operation_key_prefix="data_artifact_revision",
            producer_error_code="DATA_ARTIFACT_REVISION_FAILED",
            producer_version=result.data_input.producer_version,
            quality_failure_message="修订数据未通过研究协议的数据质量约束",
            source_mode=result.resulting_source_mode,
            snapshot_bindings_override=derive_document_snapshot_bindings(
                result.data_input
            ),
            source_snapshots=(
                authority.left_acquisition.snapshot,
                authority.right_acquisition.snapshot,
            ),
        )
        prepared = self._data_artifacts.prepare(
            context,
            step_key=step_key,
            attempt=attempt,
            lease=lease,
            data_input=result.data_input,
            config=publication_config,
            build_result=result.build_result,
        )
        build_executions_closed = False
        try:
            if alignment is not None:
                outcome = self._complete_alignment_repair(
                    context,
                    alignment=alignment,
                    quality_result=prepared.quality.evaluation_result,
                    step_key=step_key,
                    attempt=attempt,
                    lease=lease,
                )
                if outcome is not None and outcome.status == "false_repair":
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
                        error_code="DATA_ARTIFACT_REVISION_FAILED",
                    )
            raise
        publications = self._data_artifacts.publish(
            context,
            prepared=prepared,
            config=publication_config,
            publication_targets=result.publication_targets,
        )
        return PreparedStep(
            publications=publications,
            activity_result_summary=(
                "已按冻结修订计划选择性重算研究数据，共输出 "
                f"{len(result.build_result.dataset.rows)} 条规范化记录"
            ),
        )


def _repair_outcome(
    *,
    repair_state: RepairCheckpointDecisionState,
    before_defects: tuple[RepairDefect, ...],
    crossmatch: CrossmatchResult,
    quality_result: DataQualityEvaluationResult,
) -> RepairOutcome:
    assessment = assess_repair_resolution(
        decisions=repair_state.decisions,
        before_defects=before_defects,
        crossmatch=crossmatch,
    )
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
        resolved_defect_ids=assessment.resolved_defect_ids,
        unresolved_defect_ids=assessment.unresolved_defect_ids,
        status=assessment.status,
    )


__all__ = ["DataStepService"]
