"""Typed Research assistant planner over the provider-neutral model port."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.contracts.manifest_policy import validate_contract_against_manifest
from app.schemas.core import (
    ArtifactKind,
    PlannerOutcome,
    ResearchProject,
    ResearchThreadEntry,
)
from app.schemas.manifest import ManifestBundle
from app.services.model_execution import (
    ModelExecutionError,
    ModelExecutionPort,
    ModelExecutionRequest,
    ModelExecutionResponse,
)
from packages.prompts.registry import PromptRegistry


_PLANNER_OUTCOME_ADAPTER = TypeAdapter(PlannerOutcome)


@dataclass(frozen=True, slots=True)
class PlannerResult:
    output: PlannerOutcome
    request: ModelExecutionRequest
    response: ModelExecutionResponse


class ResearchContractPlanner:
    """Build a public-only planner request and validate its typed outcome."""

    def __init__(
        self,
        *,
        model_port: ModelExecutionPort,
        provider: str,
        model: str,
        model_revision: str,
        manifests: ManifestBundle,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self._model_port = model_port
        self._provider = provider
        self._model = model
        self._model_revision = model_revision
        self._manifests = manifests
        self._prompts = prompt_registry or PromptRegistry()

    def plan(
        self,
        *,
        project: ResearchProject,
        entries: tuple[ResearchThreadEntry, ...],
        message: str,
        answer_to_question_id: str | None,
    ) -> PlannerResult:
        return self.execute(
            self.prepare_request(
                project=project,
                entries=entries,
                message=message,
                answer_to_question_id=answer_to_question_id,
            )
        )

    def prepare_request(
        self,
        *,
        project: ResearchProject,
        entries: tuple[ResearchThreadEntry, ...],
        message: str,
        answer_to_question_id: str | None,
    ) -> ModelExecutionRequest:
        prompt = self._prompts.get("research_contract_planner")
        output_schema = json.dumps(
            _PLANNER_OUTCOME_ADAPTER.json_schema(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        input_payload: dict[str, Any] = {
            "message": message,
            "answer_to_question_id": answer_to_question_id,
            "project": {
                "name": project.name,
                "description": project.description,
                "case_key": project.case_key,
            },
            "planning_catalog": _planning_catalog(self._manifests),
            "output_contract": {
                "name": "PlannerOutcome",
                "json_schema": json.loads(output_schema),
            },
            "thread": [
                {
                    "sequence": entry.sequence,
                    "kind": entry.kind.value,
                    "actor": entry.actor,
                    "public_content": entry.public_content,
                    "structured_payload": entry.structured_payload,
                }
                for entry in entries[-40:]
            ],
        }
        request = ModelExecutionRequest(
            provider=self._provider,
            model=self._model,
            model_revision=self._model_revision,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            prompt_hash=prompt.content_hash,
            prompt=prompt.content,
            input_payload=input_payload,
            parameters={
                "temperature": 0,
                "top_p": 0.8,
            },
        )
        return request

    def execute(self, request: ModelExecutionRequest) -> PlannerResult:
        response = self._model_port.execute(request)
        try:
            output = _PLANNER_OUTCOME_ADAPTER.validate_python(response.payload)
        except ValidationError as exc:
            raise ModelExecutionError(
                "MODEL_RESPONSE_INVALID",
                "研究助手返回了无法验证的规划结果。",
                output_hash=response.output_hash,
                token_usage=response.token_usage,
                latency_ms=response.latency_ms,
                provider_request_id=response.provider_request_id,
            ) from exc
        if output.outcome == "draft_ready":
            try:
                validate_contract_against_manifest(
                    output.contract,
                    case_key=self._manifests.case_manifest.case_id,
                    manifests=self._manifests,
                )
            except ValueError as exc:
                raise ModelExecutionError(
                    "MODEL_RESPONSE_INVALID",
                    "研究助手生成的协议超出当前研究目录，请重试或调整研究范围。",
                    output_hash=response.output_hash,
                    token_usage=response.token_usage,
                    latency_ms=response.latency_ms,
                    provider_request_id=response.provider_request_id,
                ) from exc
        return PlannerResult(output=output, request=request, response=response)


def _planning_catalog(manifests: ManifestBundle) -> dict[str, Any]:
    case = manifests.case_manifest
    return {
        "case_id": case.case_id,
        "target_objects": [
            {
                "id": target.role,
                "object_type": target.object_type.value,
            }
            for target in case.target_objects
        ],
        "requested_fields": [
            {
                "id": field.field_id,
                "label": field.meaning_zh,
                "description": field.description,
                "canonical_unit": field.canonical_unit,
            }
            for field in manifests.field_manifest.fields
        ],
        "allowed_sources": [
            {
                "id": source_id,
                "scope": "provider",
            }
            for source_id in case.allowed_source_ids
        ],
        "default_requested_field_ids": list(case.default_requested_fields),
        "output_requirement_ids": [kind.value for kind in ArtifactKind],
    }


__all__ = ["PlannerResult", "ResearchContractPlanner"]
