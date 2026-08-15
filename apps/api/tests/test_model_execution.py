from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx2
import pytest
from openai import APIStatusError, OpenAI

import app.services.model_execution as model_execution_module
from app.schemas.core import ArtifactKind, ResearchProject
from app.schemas.manifest import load_manifest_bundle
from app.services.model_execution import (
    ModelExecutionError,
    ModelExecutionRequest,
    ModelRuntimeUnavailable,
    QwenModelExecutionAdapter,
    qwen_execution_lease_duration,
)
from app.services.research_planner import ResearchContractPlanner
from packages.prompts.registry import PromptRegistry


_MANIFEST_ROOT = (
    Path(__file__).resolve().parents[3]
    / "services"
    / "data_pipeline"
    / "manifests"
    / "exoplanet_host_star"
)


class FakeClient:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:  # noqa: ANN401
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs: Any) -> Any:  # noqa: ANN401
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def _load_case_manifests():
    return load_manifest_bundle(
        _MANIFEST_ROOT / "case-manifest.json",
        _MANIFEST_ROOT / "field-manifest.json",
    )


def research_project() -> ResearchProject:
    return ResearchProject.model_validate(
        {
            "id": "proj_1",
            "session_id": "sess_1",
            "name": "Research",
            "description": "",
            "case_key": "exoplanet_host_star",
            "thread_summary": {
                "has_thread_entries": False,
                "latest_thread_actor": None,
                "has_unanswered_clarification": False,
            },
            "created_at": "2026-07-21T08:00:00Z",
            "updated_at": "2026-07-21T08:00:00Z",
            "revision": 1,
        }
    )


def request() -> ModelExecutionRequest:
    return ModelExecutionRequest(
        provider="qwen",
        model="qwen3.7-plus",
        model_revision="qwen3.7-plus-2026-05-26",
        prompt_name="research_contract_planner",
        prompt_version="1.0.0",
        prompt_hash="sha256:" + "a" * 64,
        prompt="Return one JSON planner outcome.",
        input_payload={"message": "Compare two host stars"},
        parameters={"temperature": 0, "top_p": 0.8},
    )


def successful_response() -> Any:  # noqa: ANN401
    usage = SimpleNamespace(
        model_dump=lambda **_kwargs: {"prompt_tokens": 10, "completion_tokens": 12}
    )
    return SimpleNamespace(
        id="req_123",
        _request_id="provider-123",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"outcome":"partial","public_analysis":"需要补充字段。","assistant_message":"请补充字段。","missing_information":["requested_fields"]}'
                )
            )
        ],
        usage=usage,
    )


def test_qwen_adapter_fails_closed_without_credentials() -> None:
    client = FakeClient(successful_response())
    adapter = QwenModelExecutionAdapter(
        api_key=None,
        base_url="https://dashscope.example/v1",
        timeout_seconds=3,
        client=cast(OpenAI, client),
    )

    with pytest.raises(ModelRuntimeUnavailable) as captured:
        adapter.execute(request())

    assert captured.value.code == "MODEL_RUNTIME_UNAVAILABLE"
    assert client.calls == []


def test_qwen_adapter_uses_the_sdk_route_and_exact_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient(successful_response())
    constructor: dict[str, Any] = {}

    def build_client(**kwargs: Any) -> OpenAI:  # noqa: ANN401
        constructor.update(kwargs)
        return cast(OpenAI, client)

    monkeypatch.setattr(model_execution_module, "OpenAI", build_client)
    adapter = QwenModelExecutionAdapter(
        api_key="test-secret",
        base_url="https://dashscope.example/compatible-mode/v1/",
        timeout_seconds=7.5,
        max_retries=4,
    )

    response = adapter.execute(request())

    call = client.calls[0]
    assert constructor["base_url"] == "https://dashscope.example/compatible-mode/v1"
    assert constructor["timeout"] == 7.5
    assert constructor["max_retries"] == 4
    assert call["model"] == "qwen3.7-plus-2026-05-26"
    assert call["response_format"] == {"type": "json_object"}
    assert call["extra_body"] == {"enable_thinking": False}
    assert "max_tokens" not in call
    assert response.payload["outcome"] == "partial"
    assert response.output_hash.startswith("sha256:")
    assert response.token_usage == {"prompt_tokens": 10, "completion_tokens": 12}
    assert response.provider_request_id == "provider-123"


def test_qwen_adapter_maps_semantic_output_limit_to_transport_parameter() -> None:
    client = FakeClient(successful_response())
    adapter = QwenModelExecutionAdapter(
        api_key="test-secret",
        base_url="https://dashscope.example/v1",
        timeout_seconds=3,
        client=cast(OpenAI, client),
    )
    semantic_request = replace(
        request(), parameters={"temperature": 0, "max_output_tokens": 2048}
    )

    adapter.execute(semantic_request)

    assert client.calls[0]["max_tokens"] == 2048
    assert "max_output_tokens" not in client.calls[0]


@pytest.mark.parametrize(
    "parameters",
    (
        {"response_format": "json_schema"},
        {"extra_body": {"enable_thinking": True}},
        {"tools": []},
        {"unknown_provider_switch": True},
        {"max_tokens": 1024, "max_output_tokens": 2048},
    ),
)
def test_qwen_adapter_rejects_transport_owned_or_unknown_parameters(
    parameters: dict[str, Any],
) -> None:
    client = FakeClient(successful_response())
    adapter = QwenModelExecutionAdapter(
        api_key="test-secret",
        base_url="https://dashscope.example/v1",
        timeout_seconds=3,
        client=cast(OpenAI, client),
    )
    unsafe_request = replace(request(), parameters=parameters)

    with pytest.raises(ModelExecutionError) as captured:
        adapter.execute(unsafe_request)

    assert captured.value.code == "MODEL_REQUEST_INVALID"
    assert client.calls == []


def test_qwen_execution_lease_covers_all_attempts_and_retry_after_waits() -> None:
    assert qwen_execution_lease_duration(
        timeout_seconds=45,
        max_retries=2,
        grace_seconds=30,
    ) == timedelta(seconds=405)


@pytest.mark.parametrize(
    ("status_code", "code"),
    [
        (429, "MODEL_RATE_LIMITED"),
        (500, "MODEL_PROVIDER_UNAVAILABLE"),
        (400, "MODEL_PROVIDER_REJECTED"),
    ],
)
def test_qwen_adapter_maps_provider_failures_without_leaking_body(
    status_code: int,
    code: str,
) -> None:
    provider_request = httpx2.Request(
        "POST", "https://dashscope.example/compatible-mode/v1/chat/completions"
    )
    provider_response = httpx2.Response(status_code, request=provider_request)
    client = FakeClient(
        error=APIStatusError(
            "provider rejected request",
            response=provider_response,
            body={"secret": "do-not-return"},
        )
    )
    adapter = QwenModelExecutionAdapter(
        api_key="test-secret",
        base_url="https://dashscope.example/v1",
        timeout_seconds=3,
        client=cast(OpenAI, client),
    )

    with pytest.raises(ModelExecutionError) as captured:
        adapter.execute(request())

    assert captured.value.code == code
    assert "do-not-return" not in captured.value.public_message
    assert captured.value.latency_ms is not None


def test_qwen_adapter_distinguishes_exhausted_provider_quota() -> None:
    provider_request = httpx2.Request(
        "POST", "https://dashscope.example/compatible-mode/v1/chat/completions"
    )
    provider_response = httpx2.Response(403, request=provider_request)
    client = FakeClient(
        error=APIStatusError(
            "provider rejected request",
            response=provider_response,
            body={
                "code": "AllocationQuota.FreeTierOnly",
                "message": "provider account details must remain private",
            },
        )
    )
    adapter = QwenModelExecutionAdapter(
        api_key="test-secret",
        base_url="https://dashscope.example/v1",
        timeout_seconds=3,
        client=cast(OpenAI, client),
    )

    with pytest.raises(ModelExecutionError) as captured:
        adapter.execute(request())

    assert captured.value.code == "MODEL_QUOTA_EXHAUSTED"
    assert captured.value.public_message == (
        "研究助手调用额度已用尽，请联系管理员检查模型配额。"
    )
    assert "provider account details" not in captured.value.public_message


def test_qwen_adapter_keeps_safe_execution_metadata_for_invalid_content() -> None:
    response = successful_response()
    response.choices[0].message.content = "not-json"
    client = FakeClient(response)
    adapter = QwenModelExecutionAdapter(
        api_key="test-secret",
        base_url="https://dashscope.example/v1",
        timeout_seconds=3,
        client=cast(OpenAI, client),
    )

    with pytest.raises(ModelExecutionError) as captured:
        adapter.execute(request())

    assert captured.value.code == "MODEL_RESPONSE_INVALID"
    assert captured.value.output_hash is not None
    assert captured.value.token_usage == {
        "prompt_tokens": 10,
        "completion_tokens": 12,
    }
    assert captured.value.latency_ms is not None
    assert captured.value.provider_request_id == "provider-123"


def test_planner_rejects_untyped_model_payload() -> None:
    class Port:
        def execute(self, _request: ModelExecutionRequest):
            from app.services.model_execution import ModelExecutionResponse

            return ModelExecutionResponse(
                payload={
                    "outcome": "draft_ready",
                    "assistant_message": "missing contract",
                },
                output_hash="sha256:" + "b" * 64,
                token_usage=None,
                latency_ms=1,
                provider_request_id=None,
            )

    planner = ResearchContractPlanner(
        model_port=Port(),
        provider="qwen",
        model="qwen3.7-plus",
        model_revision="qwen3.7-plus-2026-05-26",
        manifests=_load_case_manifests(),
    )
    with pytest.raises(ModelExecutionError) as captured:
        planner.plan(
            project=research_project(),
            entries=(),
            message="Compare host stars",
            answer_to_question_id=None,
        )

    assert captured.value.code == "MODEL_RESPONSE_INVALID"


def test_planner_rejects_typed_draft_outside_manifest_catalog() -> None:
    class Port:
        def execute(self, _request: ModelExecutionRequest):
            from app.services.model_execution import ModelExecutionResponse

            return ModelExecutionResponse(
                payload={
                    "outcome": "draft_ready",
                    "public_analysis": "已整理研究范围。",
                    "assistant_message": "请确认协议。",
                    "contract": {
                        "research_goal": "Compare host stars",
                        "target_objects": ["host_star"],
                        "data_requirements": {"unit_policy": "canonical"},
                        "requested_fields": ["invented.observation_bias"],
                        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
                        "paper_search_scope": {},
                        "output_requirements": ["dataset"],
                        "evidence_requirements": {},
                        "quality_constraints": {},
                    },
                },
                output_hash="sha256:" + "b" * 64,
                token_usage=None,
                latency_ms=1,
                provider_request_id=None,
            )

    planner = ResearchContractPlanner(
        model_port=Port(),
        provider="qwen",
        model="qwen3.7-plus",
        model_revision="qwen3.7-plus-2026-05-26",
        manifests=_load_case_manifests(),
    )
    with pytest.raises(ModelExecutionError) as captured:
        planner.plan(
            project=research_project(),
            entries=(),
            message="Compare host stars",
            answer_to_question_id=None,
        )

    assert captured.value.code == "MODEL_RESPONSE_INVALID"


def test_planner_uses_the_registered_prompt_and_identified_output_contract() -> None:
    class UnusedPort:
        def execute(self, _request: ModelExecutionRequest):
            raise AssertionError("prepare_request must not execute the provider")

    planner = ResearchContractPlanner(
        model_port=UnusedPort(),
        provider="qwen",
        model="qwen3.7-plus",
        model_revision="qwen3.7-plus-2026-05-26",
        manifests=_load_case_manifests(),
    )
    request_value = planner.prepare_request(
        project=research_project(),
        entries=(),
        message="Compare host stars",
        answer_to_question_id=None,
    )

    output_contract = request_value.input_payload["output_contract"]
    assert output_contract["name"] == "PlannerOutcome"
    rendered_schema = str(output_contract["json_schema"])
    assert "question_id" in rendered_schema
    assert "contract" in rendered_schema
    catalog = request_value.input_payload["planning_catalog"]
    assert catalog["case_id"] == "exoplanet_host_star"
    assert catalog["target_objects"] == [
        {"id": "exoplanet_candidate", "object_type": "planet"},
        {"id": "host_star", "object_type": "star"},
    ]
    assert catalog["allowed_sources"] == [
        {"id": "nasa_exoplanet_archive", "scope": "provider"}
    ]
    assert [field["id"] for field in catalog["requested_fields"]] == catalog[
        "default_requested_field_ids"
    ]
    assert catalog["requested_fields"][0]["label"]
    assert catalog["output_requirement_ids"] == [kind.value for kind in ArtifactKind]
    assert catalog["executable_output_requirement_ids"] == [
        kind.value for kind in ArtifactKind if kind is not ArtifactKind.export
    ]
    assert catalog["unsupported_output_requirement_ids"] == [ArtifactKind.export.value]
    assert (
        request_value.prompt_hash
        == PromptRegistry().get("research_contract_planner").content_hash
    )
