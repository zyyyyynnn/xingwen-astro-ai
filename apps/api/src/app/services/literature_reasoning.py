"""Execute version-pinned Claim and Relation model requests before admission."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping, Sequence

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.literature_claim import LiteratureClaimAdmissionResult
from app.schemas.literature_relation import (
    LiteratureRelationAdmissionResult,
    LiteratureRelationConfidenceAssessment,
)
from app.services.model_execution import (
    ModelExecutionPort,
    ModelExecutionRequest,
    ModelExecutionResponse,
)
from services.paper_pipeline.claim import (
    LiteratureClaimExecutionPlan,
    LiteratureClaimPipeline,
    PaperSummaryArtifactVersionInput,
)
from services.paper_pipeline.relation import (
    LiteratureClaimsArtifactVersionInput,
    LiteratureRelationExecutionPlan,
    LiteratureRelationPipeline,
)


_MODEL_PARAMETERS: dict[str, str | int | float | bool | None] = {
    "temperature": 0,
    "max_output_tokens": 16_384,
}


@dataclass(frozen=True, slots=True)
class PreparedClaimExecution:
    paper_summary_version: PaperSummaryArtifactVersionInput
    run_id: str
    model_request: ModelExecutionRequest
    plan: LiteratureClaimExecutionPlan


@dataclass(frozen=True, slots=True)
class PreparedRelationExecution:
    project_id: str
    claim_versions: tuple[LiteratureClaimsArtifactVersionInput, ...]
    run_id: str
    model_request: ModelExecutionRequest
    plan: LiteratureRelationExecutionPlan
    confidence_assessments: Mapping[str, LiteratureRelationConfidenceAssessment]


@dataclass(frozen=True, slots=True)
class ClaimExecution:
    admission: LiteratureClaimAdmissionResult
    provider_request_id: str | None
    token_usage: dict[str, int] | None
    latency_ms: int


@dataclass(frozen=True, slots=True)
class RelationExecution:
    admission: LiteratureRelationAdmissionResult
    provider_request_id: str | None
    token_usage: dict[str, int] | None
    latency_ms: int


class LiteratureReasoningService:
    """Bounded model execution followed by the authoritative paper pipelines."""

    def __init__(
        self,
        model_execution: ModelExecutionPort,
        *,
        provider: str,
        model: str,
        model_revision: str,
        claim_pipeline: LiteratureClaimPipeline | None = None,
        relation_pipeline: LiteratureRelationPipeline | None = None,
    ) -> None:
        self._models = model_execution
        self._provider = provider
        self._model = model
        self._model_revision = model_revision
        self._claims = claim_pipeline or LiteratureClaimPipeline()
        self._relations = relation_pipeline or LiteratureRelationPipeline()

    def prepare_claim(
        self,
        *,
        paper_summary_version: PaperSummaryArtifactVersionInput,
        run_id: str,
    ) -> PreparedClaimExecution:
        content = paper_summary_version.content
        plan = self._claims.prepare_execution(
            paper_summary_artifact_version_id=(
                paper_summary_version.artifact_version_id
            ),
            paper_id=content.paper_id,
            paper_summary_versions={
                paper_summary_version.artifact_version_id: paper_summary_version
            },
            model_name=self._model,
            parameters=_MODEL_PARAMETERS,
        )
        input_payload = {
            "paper_summary_artifact": {
                "artifact_version_id": paper_summary_version.artifact_version_id,
                "schema_version": paper_summary_version.schema_version,
                "content": content.model_dump(mode="json", exclude_none=True),
            }
        }
        return PreparedClaimExecution(
            paper_summary_version=paper_summary_version,
            run_id=run_id,
            plan=plan,
            model_request=ModelExecutionRequest(
                provider=self._provider,
                model=self._model,
                model_revision=self._model_revision,
                prompt_name=plan.prompt_name,
                prompt_version=plan.prompt_version,
                prompt_hash=plan.prompt_hash,
                prompt=plan.prompt,
                input_payload=input_payload,
                parameters=dict(_MODEL_PARAMETERS),
            ),
        )

    def execute_prepared_claim(
        self,
        prepared: PreparedClaimExecution,
        *,
        producer_execution_id: str,
    ) -> ClaimExecution:
        response = self._models.execute(prepared.model_request)
        _validate_response(response)
        version = prepared.paper_summary_version
        content = version.content
        admission = self._claims.admit(
            paper_summary_artifact_version_id=version.artifact_version_id,
            paper_id=content.paper_id,
            paper_summary_versions={version.artifact_version_id: version},
            model_response=_response_json(response),
            model_name=self._model,
            parameters=_MODEL_PARAMETERS,
            execution_id=producer_execution_id,
            run_id=prepared.run_id,
            available_evidence_ids=frozenset(content.evidence_ids),
            available_source_snapshot_ids=frozenset(
                item.source_snapshot_id
                for item in content.input_versions.source_snapshots
            ),
        )
        if admission.producer.input_hash != prepared.plan.input_hash:
            raise ValueError("prepared Claim input identity drifted during admission")
        return ClaimExecution(
            admission=admission,
            provider_request_id=response.provider_request_id,
            token_usage=response.token_usage,
            latency_ms=response.latency_ms,
        )

    def prepare_relation(
        self,
        *,
        project_id: str,
        claim_versions: Sequence[LiteratureClaimsArtifactVersionInput],
        run_id: str,
        confidence_assessments: Mapping[
            str, LiteratureRelationConfidenceAssessment
        ] | None = None,
    ) -> PreparedRelationExecution:
        assessments = confidence_assessments or {}
        versions = tuple(claim_versions)
        version_by_id = {item.artifact_version_id: item for item in versions}
        if not versions or len(version_by_id) != len(versions):
            raise ValueError("Relation execution requires unique Claim versions")
        evidence_ids = frozenset(
            evidence_id
            for item in versions
            for evidence_id in item.content.evidence_ids
        )
        snapshot_ids = frozenset(
            snapshot_id
            for item in versions
            for snapshot_id in item.content.source_snapshot_ids
        )
        summary_version_ids = frozenset(
            claim.source_paper_summary_artifact_version_id
            for item in versions
            for claim in item.content.claims
        )
        plan = self._relations.prepare_execution(
            literature_claim_artifact_version_ids=tuple(sorted(version_by_id)),
            literature_claim_versions=version_by_id,
            project_id=project_id,
            model_name=self._model,
            parameters=_MODEL_PARAMETERS,
            confidence_assessments=assessments,
            available_evidence_ids=evidence_ids,
            available_source_snapshot_ids=snapshot_ids,
            available_paper_summary_artifact_version_ids=summary_version_ids,
        )
        input_payload = {
            "literature_claims": [
                {
                    "artifact_version_id": item.artifact_version_id,
                    "schema_version": item.schema_version,
                    "content_hash": item.content_hash,
                    "content": item.content.model_dump(
                        mode="json", exclude_none=True
                    ),
                }
                for item in sorted(versions, key=lambda value: value.artifact_version_id)
            ],
            "confidence_assessments": [
                value.model_dump(mode="json", exclude_none=True)
                for _, value in sorted(assessments.items())
            ],
        }
        return PreparedRelationExecution(
            project_id=project_id,
            claim_versions=versions,
            run_id=run_id,
            plan=plan,
            confidence_assessments=dict(assessments),
            model_request=ModelExecutionRequest(
                provider=self._provider,
                model=self._model,
                model_revision=self._model_revision,
                prompt_name=plan.prompt_name,
                prompt_version=plan.prompt_version,
                prompt_hash=plan.prompt_hash,
                prompt=plan.prompt,
                input_payload=input_payload,
                parameters=dict(_MODEL_PARAMETERS),
            ),
        )

    def execute_prepared_relation(
        self,
        prepared: PreparedRelationExecution,
        *,
        producer_execution_id: str,
    ) -> RelationExecution:
        response = self._models.execute(prepared.model_request)
        _validate_response(response)
        version_by_id = {
            item.artifact_version_id: item for item in prepared.claim_versions
        }
        evidence_ids = frozenset(
            evidence_id
            for item in prepared.claim_versions
            for evidence_id in item.content.evidence_ids
        )
        snapshot_ids = frozenset(
            snapshot_id
            for item in prepared.claim_versions
            for snapshot_id in item.content.source_snapshot_ids
        )
        summary_version_ids = frozenset(
            claim.source_paper_summary_artifact_version_id
            for item in prepared.claim_versions
            for claim in item.content.claims
        )
        admission = self._relations.admit(
            literature_claim_artifact_version_ids=tuple(sorted(version_by_id)),
            literature_claim_versions=version_by_id,
            project_id=prepared.project_id,
            model_response=_response_json(response),
            model_name=self._model,
            parameters=_MODEL_PARAMETERS,
            confidence_assessments=prepared.confidence_assessments,
            execution_id=producer_execution_id,
            run_id=prepared.run_id,
            available_evidence_ids=evidence_ids,
            available_source_snapshot_ids=snapshot_ids,
            available_paper_summary_artifact_version_ids=summary_version_ids,
        )
        if admission.producer.input_hash != prepared.plan.input_hash:
            raise ValueError("prepared Relation input identity drifted during admission")
        return RelationExecution(
            admission=admission,
            provider_request_id=response.provider_request_id,
            token_usage=response.token_usage,
            latency_ms=response.latency_ms,
        )


def _validate_response(response: ModelExecutionResponse) -> None:
    if response.latency_ms < 0:
        raise ValueError("model response latency must be non-negative")
    if response.output_hash != compute_canonical_payload_hash(response.payload):
        raise ValueError("model response output hash mismatch")


def _response_json(response: ModelExecutionResponse) -> str:
    return json.dumps(
        response.payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = [
    "ClaimExecution",
    "LiteratureReasoningService",
    "PreparedClaimExecution",
    "PreparedRelationExecution",
    "RelationExecution",
]
