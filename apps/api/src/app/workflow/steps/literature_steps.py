"""Literature reasoning step service for Research Runs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.artifact_publication import canonical_artifact_content_payload
from app.schemas.literature_claim import (
    LiteratureClaimCandidate,
    LiteratureClaimsCandidate,
    LiteratureClaimStatus,
)
from app.schemas.literature_relation import (
    LiteratureRelationConfidenceAssessment,
    LiteratureRelationsCandidate,
    LiteratureRelationStatus,
)
from app.schemas.paper_summary import PaperSummaryArtifactContent
from app.services.artifacts import ArtifactReadService
from app.services.literature_claim_chunks import ChunkedLiteratureClaimService
from app.services.paper_summaries import PaperSummaryReadPort
from app.workflow.publisher import ArtifactPublication, admit_artifact_candidate
from app.workflow.step_publication import (
    PreparedStep,
    RunStepContext,
    StepModelCaller,
    StepPublicationFactory,
    step_uuid,
)
from app.workflow.store import AttemptHandle, LeaseGrant
from services.data_pipeline.revision import DataRevisionError, DataRevisionErrorCode
from services.paper_pipeline.claim import (
    LiteratureClaimPipeline,
    PaperSummaryArtifactVersionInput,
    build_literature_claim_input_identity,
)
from services.paper_pipeline.constants import (
    CLAIM_PRODUCER_NAME,
    CLAIM_PRODUCER_VERSION,
    RELATION_ADJUDICATION_PRODUCER_NAME,
    RELATION_ADJUDICATION_PRODUCER_VERSION,
    RELATION_PARAMETERS_VERSION,
    RELATION_PRODUCER_NAME,
    RELATION_PRODUCER_VERSION,
)
from services.paper_pipeline.errors import LiteratureAdmissionExecutionError
from services.paper_pipeline.relation import (
    LiteratureClaimsArtifactVersionInput,
    LiteratureRelationPipeline,
    compute_literature_relation_adjudication_input_hash,
)
from services.paper_pipeline.relation_confidence import (
    build_live_relation_confidence_assessments,
)
from services.paper_pipeline.relation_pairing import (
    select_literature_relation_model_policy,
)

#: Governed generation parameters shared by the literature model calls.
MODEL_PARAMETERS: dict[str, float | int] = {
    "temperature": 0.6,
    "top_p": 0.8,
    "max_tokens": 8192,
}

#: Product capacity for one reviewable relation synthesis batch.
MAX_RELATION_CANDIDATES = 1
MAX_RELATION_MODEL_PAIRS = 64


class RelationConfidenceBuilder(Protocol):
    """Attempt-local confidence boundary used by the literature step."""

    def __call__(
        self,
        *,
        claim_artifact_version_id: str,
        claims: Iterable[LiteratureClaimCandidate],
    ) -> dict[str, LiteratureRelationConfidenceAssessment]: ...


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


def _relation_claim_model_input(
    claim: LiteratureClaimCandidate,
) -> dict[str, object]:
    """Project only scientific endpoint fields required by Relation synthesis."""

    return {
        "claim_id": claim.claim_id,
        "source_statement_id": claim.source_statement_id,
        "text": claim.text,
        "normalized_text": claim.normalized_text,
        "claim_type": claim.claim_type.value,
        "polarity": claim.polarity.value,
        "objects": list(claim.objects),
        "metric": claim.metric,
        "unit": claim.unit,
        "conditions": list(claim.conditions),
        "scope": list(claim.scope),
        "limitations": list(claim.limitations),
        "qualifiers": list(claim.qualifiers),
        "uncertainty": claim.uncertainty,
        "comparison_basis": claim.comparison_basis,
        "evidence_ids": list(claim.evidence_ids),
        "status": claim.status.value,
    }


class LiteratureStepService:
    """Extract and admit literature claims and relations for one Run."""

    def __init__(
        self,
        *,
        publications: StepPublicationFactory,
        summary_reader: PaperSummaryReadPort,
        relation_confidence_builder: RelationConfidenceBuilder | None = None,
    ) -> None:
        self._publications = publications
        self._summary_reader = summary_reader
        self._relation_confidence_builder = (
            relation_confidence_builder or build_live_relation_confidence_assessments
        )

    def _prepare_claims(
        self,
        *,
        context: RunStepContext,
        summary: PaperSummaryArtifactContent,
        summary_version_id: UUID,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
        model_caller: StepModelCaller,
        snapshot_bindings_override: dict[str, str],
    ) -> tuple[
        LiteratureClaimsCandidate,
        tuple[LiteratureClaimCandidate, ...],
        ArtifactPublication | None,
        UUID,
    ]:
        if context.relation_adjudications:
            claims_version_id = context.versions.get("literature_claims")
            if claims_version_id is None:
                raise ValueError(
                    "Relation adjudication requires the frozen LiteratureClaims version"
                )
            version = ArtifactReadService(self._publications.factory).get_version(
                version_id=str(claims_version_id),
                session_id=context.session_id,
                full_content=True,
            )
            claims = LiteratureClaimsCandidate.model_validate(version.content)
            context.literature_claims = claims
            return claims, claims.claims, None, claims_version_id

        claims_version_id = step_uuid(
            str(context.run_id), "artifact-version:literature_claims"
        )
        summary_versions = {
            str(summary_version_id): PaperSummaryArtifactVersionInput(
                artifact_version_id=str(summary_version_id),
                schema_version=summary.schema_version,
                content=summary,
            )
        }
        prompt = model_caller.prompt("literature_claim")
        model_execution = model_caller.pin_resumable_port()
        model_identity = model_caller.identity
        _, claim_input_hash, parameters_hash = build_literature_claim_input_identity(
            paper_summary_artifact_version_id=str(summary_version_id),
            paper_id=summary.paper_id,
            paper_summary_versions=summary_versions,
            model_name=model_identity.requested_model,
            parameters=MODEL_PARAMETERS,
        )
        claims_execution = self._publications.start_producer(
            context,
            step_key=step_key,
            operation_key="literature_claim_extraction",
            producer_type="model",
            producer_name=CLAIM_PRODUCER_NAME,
            producer_version=CLAIM_PRODUCER_VERSION,
            input_hash=claim_input_hash,
            parameters={
                **MODEL_PARAMETERS,
                "resume_from_completed_children": True,
            },
            parameters_hash=parameters_hash,
            model_provider=model_identity.provider,
            requested_model=model_identity.requested_model,
            explicit_revision=model_identity.explicit_revision,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            prompt_hash=prompt.content_hash,
            attempt=attempt,
            lease=lease,
        )
        claims_execution_id = claims_execution.id
        claims_terminalized = False
        claims_response = None
        try:
            chunked = ChunkedLiteratureClaimService(model_execution).execute(
                summary=summary,
                paper_summary_artifact_version_id=str(summary_version_id),
                provider=model_identity.provider,
                model=model_identity.requested_model,
                model_revision=model_identity.explicit_revision,
                parameters=MODEL_PARAMETERS,
            )
            claims_response = chunked.model_response
            claims_model_response = json.dumps(
                chunked.extraction.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            claims_result = LiteratureClaimPipeline().admit(
                paper_summary_artifact_version_id=str(summary_version_id),
                paper_id=summary.paper_id,
                paper_summary_versions=summary_versions,
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
                    error_code=(
                        f"LITERATURE_CLAIM_{claims_result.failure_stage or 'REJECTED'}"
                    ),
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
                self._publications.finish_producer(
                    claims_execution_id,
                    status="failed",
                    output_hash=(
                        claims_response.output_hash
                        if claims_response is not None
                        else None
                    ),
                    response=claims_response,
                    error_code=(
                        "LITERATURE_CLAIM_POST_PROVIDER_LOCAL_FAILURE"
                        if claims_response is not None
                        else "LITERATURE_CLAIM_EXECUTION_FAILED"
                    ),
                )
            raise
        publication = self._publications.publication(
            context,
            kind="literature_claims",
            candidate=admitted_claims,
            producer_execution_id=claims_execution_id,
            version_id=claims_version_id,
        )
        return claims, claims_result.records, publication, claims_version_id

    def _prepare_adjudicated_relations(
        self,
        *,
        context: RunStepContext,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
        claims: LiteratureClaimsCandidate,
        claim_records: tuple[LiteratureClaimCandidate, ...],
        claims_version_id: UUID,
        relation_input: LiteratureClaimsArtifactVersionInput,
        snapshot_bindings_override: dict[str, str],
    ) -> tuple[LiteratureRelationsCandidate, ArtifactPublication, int]:
        del claim_records
        del relation_input
        baseline_version_id = context.versions.get("literature_relations")
        if baseline_version_id is None:
            raise DataRevisionError(
                DataRevisionErrorCode.replan_required,
                "Relation adjudication requires the frozen LiteratureRelations version",
            )
        baseline_version = ArtifactReadService(self._publications.factory).get_version(
            version_id=str(baseline_version_id),
            session_id=context.session_id,
            full_content=True,
        )
        baseline = LiteratureRelationsCandidate.model_validate(baseline_version.content)
        adjudications = dict(context.relation_adjudications)
        algorithm_input_hash = compute_literature_relation_adjudication_input_hash(
            baseline_relation_artifact_version_id=str(baseline_version_id),
            baseline_relation_content_hash=baseline_version.content_hash,
            literature_claim_artifact_version_id=str(claims_version_id),
            adjudications=adjudications.values(),
        )
        execution = self._publications.start_producer(
            context,
            step_key=step_key,
            operation_key="literature_relation_adjudication",
            producer_type="algorithm",
            producer_name=RELATION_ADJUDICATION_PRODUCER_NAME,
            producer_version=RELATION_ADJUDICATION_PRODUCER_VERSION,
            input_hash=algorithm_input_hash,
            parameters={"adjudication_count": len(adjudications)},
            attempt=attempt,
            lease=lease,
        )
        terminalized = False
        try:
            try:
                relations = LiteratureRelationPipeline().adjudicate(
                    baseline=baseline,
                    baseline_artifact_version_id=str(baseline_version_id),
                    literature_claim_artifact_version_id=str(claims_version_id),
                    adjudications=adjudications,
                )
            except ValueError as exc:
                raise DataRevisionError(
                    DataRevisionErrorCode.replan_required, str(exc)
                ) from exc
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
            self._publications.finish_producer(
                execution.id,
                status="completed",
                output_hash=admitted_relations.content_hash,
            )
            terminalized = True
        except Exception:
            if not terminalized:
                self._publications.finish_producer(
                    execution.id,
                    status="failed",
                    error_code="LITERATURE_RELATION_ADJUDICATION_FAILED",
                )
            raise
        publication = self._publications.publication(
            context,
            kind="literature_relations",
            candidate=admitted_relations,
            producer_execution_id=execution.id,
            version_id=None,
        )
        return relations, publication, len(relations.relations)

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
        snapshot_bindings_override: dict[str, str] = {}
        if summary.input_versions.document_parses:
            for snap in summary.input_versions.source_snapshots:
                snapshot_bindings_override[str(snap.source_snapshot_id)] = str(
                    snap.source_snapshot_id
                )

        claims, claim_records, claims_publication, claims_version_id = (
            self._prepare_claims(
                context=context,
                summary=summary,
                summary_version_id=summary_version_id,
                step_key=step_key,
                attempt=attempt,
                lease=lease,
                model_caller=model_caller,
                snapshot_bindings_override=snapshot_bindings_override,
            )
        )

        relation_input = LiteratureClaimsArtifactVersionInput(
            artifact_version_id=str(claims_version_id),
            schema_version=claims.schema_version,
            content_hash=compute_canonical_payload_hash(
                canonical_artifact_content_payload(claims)
            ),
            project_id=str(context.project_id),
            content=claims,
        )
        if context.relation_adjudications:
            relations, relations_publication, relation_count = (
                self._prepare_adjudicated_relations(
                    context=context,
                    step_key=step_key,
                    attempt=attempt,
                    lease=lease,
                    claims=claims,
                    claim_records=claim_records,
                    claims_version_id=claims_version_id,
                    relation_input=relation_input,
                    snapshot_bindings_override=snapshot_bindings_override,
                )
            )
            context.literature_claims = claims
            context.literature_relations = relations
            return PreparedStep(
                publications=(relations_publication,),
                activity_result_summary=(
                    f"已按冻结候选完成 {relation_count} 条论点关系审定"
                ),
            )

        # Normal scientific-content revision: a fresh relation model output is required.
        confidence = self._relation_confidence_builder(
            claim_artifact_version_id=str(claims_version_id),
            claims=claim_records,
        )
        relation_policy = select_literature_relation_model_policy(
            claim_records,
            max_pairs=MAX_RELATION_MODEL_PAIRS,
        )
        relation_claim_ids = {
            claim_id
            for pair in relation_policy.pairs
            for claim_id in (pair.source_claim_id, pair.target_claim_id)
        }
        relations_model_response, relations_response, relations_execution_id = (
            model_caller.execute_json(
                prompt_name="literature_relation",
                input_payload={
                    "literature_claim_artifact_version_ids": [str(claims_version_id)],
                    "claims": {
                        "artifact_version_id": str(claims_version_id),
                        "schema_version": claims.schema_version,
                        "claims": [
                            _relation_claim_model_input(claim)
                            for claim in claim_records
                            if claim.claim_id in relation_claim_ids
                        ],
                    },
                    "max_relation_candidates": MAX_RELATION_CANDIDATES,
                    "relation_comparability_policy": relation_policy.as_model_input(),
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
                error_code = f"LITERATURE_RELATION_{relations_result.failure_stage or 'REJECTED'}"
                model_caller.reject(
                    relations_execution_id,
                    input_hash=None,
                    response=relations_response,
                    error_code=error_code,
                )
                relations_terminalized = True
                raise LiteratureAdmissionExecutionError(
                    code=error_code,
                    public_message="文献关系输出未通过科学准入，正在重新生成。",
                )

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
            publications=(
                (relations_publication,)
                if claims_publication is None
                else (claims_publication, relations_publication)
            ),
            activity_result_summary=(
                f"已提取 {len(claim_records)} 条科学论点与 "
                f"{len(relations_result.records)} 条论点关系"
            ),
        )


__all__ = ["LiteratureStepService"]
