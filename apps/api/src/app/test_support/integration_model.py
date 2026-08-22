"""Deterministic ModelExecutionPort for mandatory real-HTTP integration tests.

This boundary is loaded only by ``APP_ENV=integration`` when no real DashScope
credential is configured. It exercises the production ResearchContractPlanner,
ModelExecution persistence, ResearchApplicationService, PostgreSQL Thread, and
browser UI without claiming Qwen/provider qualification.
"""

from __future__ import annotations

from app.schemas.core import (
    DocumentSourcePolicy,
    UnitPolicy,
    ArtifactKind,
    DataRequirements,
    EvidenceRequirements,
    PaperSearchScope,
    PlannerDraftReady,
    ResearchContractInput,
    SourceScope,
)
from app.security import canonical_request_hash
from app.services.model_execution import ModelExecutionRequest, ModelExecutionResponse


class DeterministicIntegrationModelExecutionPort:
    """Return one manifest-bound draft for the formal integration environment."""

    model_name = "deterministic-integration-planner"
    model_revision = "integration-fixture-1"

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        catalog = request.input_payload.get("planning_catalog")
        message = request.input_payload.get("message")
        if not isinstance(catalog, dict) or not isinstance(message, str):
            raise RuntimeError("integration planner request is missing the planning catalog")

        target_objects = catalog.get("target_objects")
        default_fields = catalog.get("default_requested_field_ids")
        allowed_sources = catalog.get("allowed_sources")
        if (
            not isinstance(target_objects, list)
            or not target_objects
            or not isinstance(default_fields, list)
            or not default_fields
            or not isinstance(allowed_sources, list)
            or not allowed_sources
        ):
            raise RuntimeError("integration planning catalog is incomplete")

        target_id = target_objects[0].get("id")
        source_id = allowed_sources[0].get("id")
        if not isinstance(target_id, str) or not isinstance(source_id, str):
            raise RuntimeError("integration planning catalog identities are invalid")

        contract = ResearchContractInput(
            research_goal=message.strip(),
            target_objects=(target_id,),
            data_requirements=DataRequirements(unit_policy=UnitPolicy.canonical, document_source_policy=DocumentSourcePolicy.disabled),
            requested_fields=tuple(str(item) for item in default_fields),
            source_scope=SourceScope(allowed_sources=(source_id,)),
            paper_search_scope=PaperSearchScope(),
            output_requirements=(ArtifactKind.dataset,),
            evidence_requirements=EvidenceRequirements(),
            quality_constraints={},
        )
        outcome = PlannerDraftReady(
            outcome="draft_ready",
            public_analysis=(
                "已核对研究目标、允许的数据来源与可交付字段，接下来需要确认研究协议。"
            ),
            assistant_message=(
                "我已根据当前研究目标整理好研究协议。确认后会按冻结的研究边界开始执行。"
            ),
            warnings=(),
            contract=contract,
            project_title="系外行星研究",
        )
        payload = outcome.model_dump(mode="json")
        return ModelExecutionResponse(
            payload=payload,
            output_hash=canonical_request_hash(payload),
            token_usage=None,
            latency_ms=0,
            provider_request_id="integration-deterministic-planner",
            provider_returned_model=self.model_name,
        )


__all__ = ["DeterministicIntegrationModelExecutionPort"]
