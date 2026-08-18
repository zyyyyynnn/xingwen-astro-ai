"""Literature reasoning step service for Research Runs."""

from __future__ import annotations

from app.schemas.literature_claim import LiteratureClaimStatus
from app.schemas.literature_relation import LiteratureRelationStatus
from app.schemas.reasoning_traces import build_reasoning_traces_artifact
from app.workflow.publisher import admit_artifact_candidate
from app.workflow.step_publication import (
    PreparedStep,
    ReasoningTracesProducer,
    RunStepContext,
    StepModelCaller,
    StepPublicationFactory,
    step_uuid,
)
from app.workflow.store import AttemptHandle, LeaseGrant
from services.paper_pipeline.claim import (
    LiteratureClaimPipeline,
    PaperSummaryArtifactVersionInput,
)
from services.paper_pipeline.relation import (
    LiteratureClaimsArtifactVersionInput,
    LiteratureRelationPipeline,
)
from services.paper_pipeline.relation_confidence import (
    build_live_relation_confidence_assessments,
)

#: Governed generation parameters shared by the literature model calls.
MODEL_PARAMETERS: dict[str, float | int] = {"temperature": 0.6, "top_p": 0.8}


class LiteratureStepService:
    """Extract and admit literature claims and relations for one Run."""

    def __init__(
        self,
        *,
        publications: StepPublicationFactory,
    ) -> None:
        self._publications = publications

    def reason(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
        model_caller: StepModelCaller,
    ) -> PreparedStep:
        summary = context.paper_summary
        if summary is None:
            raise ValueError("paper_summary must be prepared first")
        summary_version_id = context.versions.get("paper_summary") or step_uuid(
            str(context.run_id), "artifact-version:paper_summary"
        )
        claims_version_id = step_uuid(
            str(context.run_id), "artifact-version:literature_claims"
        )

        claims_model_response, claims_response, claims_execution_id = model_caller.execute_json(
            prompt_name="literature_claim",
            input_payload={
                "paper_summary_artifact_version_id": str(summary_version_id),
                "paper_summary": summary.model_dump(mode="json"),
            },
            parameters=MODEL_PARAMETERS,
        )
        claims_result = LiteratureClaimPipeline().admit(
            paper_summary_artifact_version_id=str(summary_version_id),
            paper_id=summary.paper_id,
            paper_summary_versions={
                str(summary_version_id): PaperSummaryArtifactVersionInput(
                    artifact_version_id=str(summary_version_id),
                    schema_version=summary.schema_version,
                    content=summary,
                )
            },
            model_response=claims_model_response,
            model_name=model_caller.requested_model,
            parameters=MODEL_PARAMETERS,
            run_id=str(context.run_id),
            available_evidence_ids=frozenset(
                item.evidence_id for item in summary.evidence
            ),
            available_source_snapshot_ids=frozenset(summary.source_snapshot_ids),
        )
        claims = claims_result.publisher_candidate
        if claims is None or claims_result.admission_status not in {
            LiteratureClaimStatus.accepted,
            LiteratureClaimStatus.candidate,
        }:
            model_caller.reject(
                claims_execution_id,
                input_hash=None,
                response=claims_response,
                error_code=f"LITERATURE_CLAIM_{claims_result.failure_stage or 'REJECTED'}",
            )
            raise ValueError(f"文献论点未通过准入: {claims_result.failure_stage}")

        relation_input = LiteratureClaimsArtifactVersionInput(
            artifact_version_id=str(claims_version_id),
            schema_version=claims.schema_version,
            content_hash=claims.output_hash,
            project_id=str(context.project_id),
            content=claims,
        )
        confidence = build_live_relation_confidence_assessments(
            claim_artifact_version_id=str(claims_version_id),
            claims=claims_result.records,
        )
        relations_model_response, relations_response, relations_execution_id = (
            model_caller.execute_json(
                prompt_name="literature_relation",
                input_payload={
                    "literature_claim_artifact_version_ids": [str(claims_version_id)],
                    "claims": claims.model_dump(mode="json"),
                },
                parameters=MODEL_PARAMETERS,
            )
        )
        relations_result = LiteratureRelationPipeline().admit(
            literature_claim_artifact_version_ids=(str(claims_version_id),),
            literature_claim_versions={str(claims_version_id): relation_input},
            project_id=str(context.project_id),
            model_response=relations_model_response,
            model_name=model_caller.requested_model,
            parameters=MODEL_PARAMETERS,
            confidence_assessments=confidence,
            run_id=str(context.run_id),
            available_evidence_ids=frozenset(
                item.evidence_id for item in summary.evidence
            ),
            available_source_snapshot_ids=frozenset(summary.source_snapshot_ids),
            available_paper_summary_artifact_version_ids=frozenset(
                {str(summary_version_id)}
            ),
        )
        relations = relations_result.publisher_candidate
        if relations is None or relations_result.admission_status not in {
            LiteratureRelationStatus.accepted,
            LiteratureRelationStatus.candidate,
        }:
            model_caller.reject(
                relations_execution_id,
                input_hash=None,
                response=relations_response,
                error_code=f"LITERATURE_RELATION_{relations_result.failure_stage or 'REJECTED'}",
            )
            raise ValueError(f"文献关系未通过准入: {relations_result.failure_stage}")

        publications = []
        for kind, candidate, version_id, response, execution_id in (
            ("literature_claims", claims, claims_version_id, claims_response, claims_execution_id),
            ("literature_relations", relations, None, relations_response, relations_execution_id),
        ):
            source_bindings = self._publications.source_bindings(
                context, candidate.source_snapshot_ids
            )
            evidence_bindings = self._publications.literature_bindings(
                context,
                kind=kind,
                candidate=candidate,
            )
            admitted = admit_artifact_candidate(
                candidate,
                schema_version=candidate.schema_version,
                source_snapshot_ids=candidate.source_snapshot_ids,
                evidence_ids=candidate.evidence_ids,
                evidence_validator=lambda _context: None,
                domain_validator=lambda _context: None,
                quality_validator=lambda _context: None,
                source_snapshot_bindings=source_bindings,
                evidence_bindings=evidence_bindings,
            )
            model_caller.complete(
                execution_id,
                input_hash=candidate.input_hash,
                output_hash=admitted.content_hash,
                response=response,
            )
            publications.append(
                self._publications.publication(
                    context,
                    kind=kind,
                    candidate=admitted,
                    producer_execution_id=execution_id,
                    version_id=version_id,
                )
            )

        traces_artifact_id = step_uuid(
            str(context.project_id), "artifact:reasoning_traces"
        )
        traces_version_id = step_uuid(
            str(context.run_id), "artifact-version:reasoning_traces"
        )
        traces_producer = ReasoningTracesProducer()
        traces_execution = self._publications.start_producer(
            context,
            step_key=step_key,
            operation_key="reasoning_traces",
            producer_type="algorithm",
            producer_name=traces_producer.producer_name,
            producer_version=traces_producer.producer_version,
            input_hash=relations.output_hash,
            parameters={},
            attempt=attempt,
            lease=lease,
        )
        try:
            traces_candidate = build_reasoning_traces_artifact(relations)
        except Exception:
            self._publications.finish_producer(
                traces_execution.id,
                status="failed",
                error_code="REASONING_TRACE_PROJECTION_FAILED",
            )
            raise
        traces_admitted = admit_artifact_candidate(
            traces_candidate,
            schema_version=traces_candidate.schema_version,
            source_snapshot_ids=(),
            evidence_ids=(),
            evidence_validator=lambda _context: None,
            domain_validator=lambda _context: None,
            quality_validator=lambda _context: None,
            source_snapshot_bindings=(),
            evidence_bindings=(),
        )
        self._publications.finish_producer(
            traces_execution.id,
            status="completed",
            input_hash=traces_candidate.input_hash,
            output_hash=traces_admitted.content_hash,
        )
        publications.append(
            self._publications.publication(
                context,
                kind="reasoning_traces",
                candidate=traces_admitted,
                producer_execution_id=traces_execution.id,
                artifact_id=traces_artifact_id,
                version_id=traces_version_id,
            )
        )
        context.literature_claims = claims
        context.literature_relations = relations
        context.reasoning_traces_artifact_id = traces_artifact_id
        context.reasoning_traces_version_id = traces_version_id
        return PreparedStep(
            publications=tuple(publications),
            activity_result_summary=(
                f"已提取 {len(claims_result.records)} 条科学论点与 "
                f"{len(relations_result.records)} 条论点关系"
            ),
        )


__all__ = ["LiteratureStepService"]
