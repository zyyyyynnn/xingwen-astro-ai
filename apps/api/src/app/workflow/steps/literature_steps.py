"""Literature reasoning step service for Research Runs."""

from __future__ import annotations

import asyncio

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.artifact_publication import canonical_artifact_content_payload
from app.schemas.literature_claim import LiteratureClaimStatus
from app.schemas.literature_relation import LiteratureRelationStatus
from app.services.paper_summaries import PaperSummaryReadPort
from app.workflow.publisher import admit_artifact_candidate
from app.workflow.step_publication import (
    PreparedStep,
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
from services.paper_pipeline.constants import (
    CLAIM_PARAMETERS_VERSION,
    CLAIM_PRODUCER_NAME,
    CLAIM_PRODUCER_VERSION,
    RELATION_PARAMETERS_VERSION,
    RELATION_PRODUCER_NAME,
    RELATION_PRODUCER_VERSION,
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


def _claim_parameters_hash(
    parameters: dict[str, float | int],
) -> str:
    """Mirror the Claim pipeline's governed parameter-hash identity."""

    return compute_canonical_payload_hash(
        {
            "parameters_version": CLAIM_PARAMETERS_VERSION,
            "parameters": dict(parameters),
        }
    )


def _relation_parameters_hash(
    parameters: dict[str, float | int],
) -> str:
    """Mirror the Relation pipeline's governed parameter-hash identity."""

    return compute_canonical_payload_hash(
        {
            "parameters_version": RELATION_PARAMETERS_VERSION,
            "parameters": dict(parameters),
        }
    )


class LiteratureStepService:
    """Extract and admit literature claims and relations for one Run."""

    def __init__(
        self,
        *,
        publications: StepPublicationFactory,
        summary_reader: PaperSummaryReadPort,
    ) -> None:
        self._publications = publications
        self._summary_reader = summary_reader

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
        summary_version_id = context.versions.get("paper_summary")
        if summary is None and summary_version_id is not None:
            read = asyncio.run(
                self._summary_reader.get_summary(
                    version_id=str(summary_version_id),
                    session_id=context.session_id,
                )
            )
            summary = read.summary
            context.paper_summary = summary
        if summary is None:
            raise ValueError("paper_summary must be prepared first")
        if summary_version_id is None:
            summary_version_id = step_uuid(
                str(context.run_id), "artifact-version:paper_summary"
            )
        claims_version_id = step_uuid(
            str(context.run_id), "artifact-version:literature_claims"
        )

        snapshot_bindings_override: dict[str, str] = {}
        if summary.input_versions.document_parses:
            for snap in summary.input_versions.source_snapshots:
                snapshot_bindings_override[str(snap.source_snapshot_id)] = str(
                    snap.source_snapshot_id
                )

        # Claims execution, admission, bindings, terminalization, and publication prep
        claims_model_response, claims_response, claims_execution_id = model_caller.execute_json(
            prompt_name="literature_claim",
            input_payload={
                "paper_summary_artifact_version_id": str(summary_version_id),
                "paper_summary": summary.model_dump(mode="json"),
            },
            parameters=MODEL_PARAMETERS,
            producer_name=CLAIM_PRODUCER_NAME,
            producer_version=CLAIM_PRODUCER_VERSION,
            parameters_hash=_claim_parameters_hash(MODEL_PARAMETERS),
        )
        claims_terminalized = False
        try:
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
                claims_terminalized = True
                raise ValueError(f"文献论点未通过准入: {claims_result.failure_stage}")

            claims_source_bindings = self._publications.source_bindings(
                context,
                claims.source_snapshot_ids,
                snapshot_bindings_override=snapshot_bindings_override,
            )
            claims_evidence_bindings = self._publications.literature_bindings(
                context,
                kind="literature_claims",
                candidate=claims,
                snapshot_bindings_override=snapshot_bindings_override,
            )
            admitted_claims = admit_artifact_candidate(
                claims,
                schema_version=claims.schema_version,
                source_snapshot_ids=claims.source_snapshot_ids,
                evidence_ids=claims.evidence_ids,
                evidence_validator=lambda _context: None,
                domain_validator=lambda _context: None,
                quality_validator=lambda _context: None,
                source_snapshot_bindings=claims_source_bindings,
                evidence_bindings=claims_evidence_bindings,
            )
            model_caller.complete(
                claims_execution_id,
                input_hash=claims.input_hash,
                output_hash=admitted_claims.content_hash,
                response=claims_response,
            )
            claims_terminalized = True
        except Exception:
            if not claims_terminalized:
                error_code = "LITERATURE_CLAIM_POST_PROVIDER_LOCAL_FAILURE"
                self._publications.finish_producer(
                    claims_execution_id,
                    status="failed",
                    output_hash=claims_response.output_hash,
                    response=claims_response,
                    error_code=error_code,
                )
            raise
        claims_publication = self._publications.publication(
            context,
            kind="literature_claims",
            candidate=admitted_claims,
            producer_execution_id=claims_execution_id,
            version_id=claims_version_id,
        )

        # Relations execution, admission, bindings, terminalization, and publication prep
        relation_input = LiteratureClaimsArtifactVersionInput(
            artifact_version_id=str(claims_version_id),
            schema_version=claims.schema_version,
            content_hash=compute_canonical_payload_hash(
                canonical_artifact_content_payload(claims)
            ),
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
                producer_name=RELATION_PRODUCER_NAME,
                producer_version=RELATION_PRODUCER_VERSION,
                parameters_hash=_relation_parameters_hash(MODEL_PARAMETERS),
            )
        )
        relations_terminalized = False
        try:
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
                relations_terminalized = True
                raise ValueError(f"文献关系未通过准入: {relations_result.failure_stage}")

            relations_source_bindings = self._publications.source_bindings(
                context,
                relations.source_snapshot_ids,
                snapshot_bindings_override=snapshot_bindings_override,
            )
            relations_evidence_bindings = self._publications.literature_bindings(
                context,
                kind="literature_relations",
                candidate=relations,
                snapshot_bindings_override=snapshot_bindings_override,
            )
            admitted_relations = admit_artifact_candidate(
                relations,
                schema_version=relations.schema_version,
                source_snapshot_ids=relations.source_snapshot_ids,
                evidence_ids=relations.evidence_ids,
                evidence_validator=lambda _context: None,
                domain_validator=lambda _context: None,
                quality_validator=lambda _context: None,
                source_snapshot_bindings=relations_source_bindings,
                evidence_bindings=relations_evidence_bindings,
            )
            model_caller.complete(
                relations_execution_id,
                input_hash=relations.input_hash,
                output_hash=admitted_relations.content_hash,
                response=relations_response,
            )
            relations_terminalized = True
        except Exception:
            if not relations_terminalized:
                error_code = "LITERATURE_RELATION_POST_PROVIDER_LOCAL_FAILURE"
                self._publications.finish_producer(
                    relations_execution_id,
                    status="failed",
                    output_hash=relations_response.output_hash,
                    response=relations_response,
                    error_code=error_code,
                )
            raise
        relations_publication = self._publications.publication(
            context,
            kind="literature_relations",
            candidate=admitted_relations,
            producer_execution_id=relations_execution_id,
            version_id=None,
        )

        # Atomic co-output publication set
        context.literature_claims = claims
        context.literature_relations = relations
        return PreparedStep(
            publications=(claims_publication, relations_publication),
            activity_result_summary=(
                f"已提取 {len(claims_result.records)} 条科学论点与 "
                f"{len(relations_result.records)} 条论点关系"
            ),
        )


__all__ = ["LiteratureStepService"]
