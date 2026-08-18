"""Data acquisition and cleaning step services for Research Runs."""

from __future__ import annotations

from typing import Any

from app.schemas.crossmatch import (
    CrossmatchInput,
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
    step_uuid,
)
from app.workflow.store import AttemptHandle, LeaseGrant
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
    ) -> None:
        self._manifests = manifests
        self._publications = publications

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
        return PreparedStep(
            (), activity_result_summary="已按研究协议获取所需数据材料"
        )

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
        try:
            build_result = build_data_artifact_candidates(data_input)
        except Exception:
            for execution in build_executions.values():
                self._publications.finish_producer(
                    execution.id,
                    status="failed",
                    error_code="DATA_ARTIFACT_BUILD_FAILED",
                )
            raise
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


__all__ = ["DataStepService"]
