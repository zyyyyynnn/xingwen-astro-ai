"""Deterministic ModelExecutionPort for mandatory real-HTTP integration tests.

This boundary is loaded only by ``APP_ENV=integration`` when no real DashScope
credential is configured. It exercises the production ResearchContractPlanner,
ModelExecution persistence, ResearchApplicationService, PostgreSQL Thread, and
browser UI without claiming Qwen/provider qualification.
"""

from __future__ import annotations

from uuid import uuid4

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
from app.services.model_execution import (
    ModelExecutionRequest,
    ModelExecutionResponse,
    ModelToolCall,
)

_STATEMENT_A = "statement.integration.1"
_STATEMENT_B = "statement.integration.2"
_PAPER_EVIDENCE_ID = "ev.title"


class DeterministicIntegrationModelExecutionPort:
    """Return one manifest-bound draft for the formal integration environment."""

    model_name = "deterministic-integration-planner"
    model_revision = "integration-fixture-1"

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        if request.response_mode == "tool":
            return self._tool_response(request)
        if request.prompt_name == "paper_summary":
            return self._json_response(request, self._paper_summary(request))
        if request.prompt_name == "literature_claim":
            return self._json_response(request, self._literature_claims(request))
        if request.prompt_name == "literature_relation":
            return self._json_response(request, self._literature_relations(request))

        catalog = request.input_payload.get("planning_catalog")
        message = request.input_payload.get("message")
        if not isinstance(catalog, dict) or not isinstance(message, str):
            raise RuntimeError(
                "integration planner request is missing the planning catalog"
            )

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
            data_requirements=DataRequirements(
                unit_policy=UnitPolicy.canonical,
                document_source_policy=DocumentSourcePolicy.disabled,
            ),
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

    def _tool_response(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        if not request.tools:
            raise RuntimeError("integration tool request is missing its tool contract")
        tool_name = request.tools[0]["function"]["name"]
        payload: dict[str, object] = {}
        return ModelExecutionResponse(
            payload=payload,
            output_hash=canonical_request_hash({"tool": tool_name}),
            token_usage={
                "prompt_tokens": 4,
                "completion_tokens": 4,
                "total_tokens": 8,
            },
            latency_ms=0,
            provider_request_id=f"integration-tool-{tool_name}",
            provider_returned_model=self.model_name,
            tool_calls=(
                ModelToolCall(
                    id=f"integration-{uuid4()}",
                    name=tool_name,
                    arguments={
                        "public_analysis": "核对冻结研究协议与本步骤输入后继续执行。"
                    },
                ),
            ),
        )

    def _json_response(
        self,
        request: ModelExecutionRequest,
        payload: dict[str, object],
    ) -> ModelExecutionResponse:
        return ModelExecutionResponse(
            payload=payload,
            output_hash=canonical_request_hash(payload),
            token_usage={
                "prompt_tokens": 10,
                "completion_tokens": 10,
                "total_tokens": 20,
            },
            latency_ms=0,
            provider_request_id=f"integration-{request.prompt_name}",
            provider_returned_model=self.model_name,
        )

    def _paper_summary(self, request: ModelExecutionRequest) -> dict[str, object]:
        paper_payload = request.input_payload.get("paper_payload", {})
        evidence = (
            paper_payload.get("evidence") if isinstance(paper_payload, dict) else None
        )
        evidence_id = (
            evidence[0]["evidence_id"]
            if isinstance(evidence, (list, tuple))
            and evidence
            and isinstance(evidence[0], dict)
            and isinstance(evidence[0].get("evidence_id"), str)
            else _PAPER_EVIDENCE_ID
        )
        return {
            "background": (),
            "methodology": (),
            "dataset": (),
            "experiments": (
                {
                    "statement_id": _STATEMENT_A,
                    "text": "Confirmed transiting planets orbit nearby host stars.",
                    "evidence_ids": [evidence_id],
                },
                {
                    "statement_id": _STATEMENT_B,
                    "text": "Small-planet recovery methods use comparable transit signatures.",
                    "evidence_ids": [evidence_id],
                },
            ),
            "discussion": (),
            "limitations": (),
            "research_questions": (),
            "evidence_ids": [evidence_id],
        }

    def _literature_claims(self, request: ModelExecutionRequest) -> dict[str, object]:
        summary = request.input_payload.get("paper_summary", {})
        evidence_ids = (
            summary.get("evidence_ids")
            if isinstance(summary, dict) and summary.get("evidence_ids")
            else [_PAPER_EVIDENCE_ID]
        )
        claims = (
            self._claim(
                _STATEMENT_A,
                "Confirmed transiting planets orbit nearby host stars.",
                evidence_ids,
            ),
            self._claim(
                _STATEMENT_B,
                "Small-planet recovery methods share comparable transit signatures.",
                evidence_ids,
            ),
        )
        return {"schema_version": "1.0.0", "claims": claims}

    def _literature_relations(
        self, request: ModelExecutionRequest
    ) -> dict[str, object]:
        claims_bundle = request.input_payload.get("claims", {})
        claims = (
            claims_bundle.get("claims", ()) if isinstance(claims_bundle, dict) else ()
        )
        if not isinstance(claims, (list, tuple)) or len(claims) < 2:
            raise RuntimeError("integration relation fixture requires two claims")
        source_id = claims[0]["claim_id"]
        target_id = claims[1]["claim_id"]
        evidence_ids = claims[0].get("evidence_ids") or [_PAPER_EVIDENCE_ID]
        operations = (
            "identify_premises",
            "compare_objects",
            "check_conditions",
            "check_evidence",
            "classify_relation",
        )
        relation = {
            "source_claim_id": source_id,
            "target_claim_id": target_id,
            "relation_type": "compares_method",
            "direction": {
                "source_claim_id": source_id,
                "target_claim_id": target_id,
                "basis": "The comparison direction is explicit.",
            },
            "conditions": ["same catalog scope"],
            "condition_conflicts": [],
            "condition_uncertainties": [],
            "comparability": {
                "object_status": "comparable",
                "object_basis": "Both claims concern the same astronomical objects.",
                "metric_status": "not_applicable",
                "metric_basis": "Neither claim declares a metric.",
                "unit_status": "not_applicable",
                "unit_basis": "Neither claim declares a unit.",
            },
            "evidence_ids": evidence_ids,
            "trace": {
                "premise_claim_ids": [source_id, target_id],
                "steps": [
                    {
                        "order": order,
                        "operation": operation,
                        "statement": f"Auditable {operation.replace('_', ' ')} step.",
                        "claim_ids": [source_id, target_id],
                        "evidence_ids": evidence_ids,
                    }
                    for order, operation in enumerate(operations, 1)
                ],
                "conditions": ["same catalog scope"],
                "limitations": [],
                "conflicts": [],
                "conclusion": "The two claims compare methods over the same objects.",
            },
        }
        return {"schema_version": "1.0.0", "relations": (relation,)}

    @staticmethod
    def _claim(
        statement_id: str,
        text: str,
        evidence_ids: object,
    ) -> dict[str, object]:
        return {
            "source_statement_id": statement_id,
            "text": text,
            "normalized_text": text.lower(),
            "claim_type": "finding",
            "polarity": "positive",
            "objects": ("nearby host stars",),
            "metric": None,
            "unit": None,
            "conditions": (),
            "scope": (),
            "limitations": (),
            "qualifiers": (),
            "uncertainty": None,
            "comparison_basis": None,
            "evidence_ids": evidence_ids,
        }


__all__ = ["DeterministicIntegrationModelExecutionPort"]
