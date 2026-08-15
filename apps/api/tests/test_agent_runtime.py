from __future__ import annotations

from app.schemas.core import ScientificSkillId
from app.schemas._hashing import compute_canonical_payload_hash
from app.services.model_execution import (
    ModelExecutionRequest,
    ModelExecutionResponse,
    ModelToolCall,
)
from app.workflow.agent_runtime import AgentSelectionValidationError, ResearchStepAgent
from packages.prompts.registry import PromptRegistry


class _Model:
    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        self.requests: list[ModelExecutionRequest] = []

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        self.requests.append(request)
        return ModelExecutionResponse(
            payload={},
            output_hash="sha256:" + "a" * 64,
            token_usage={
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "total_tokens": 14,
            },
            latency_ms=3,
            provider_request_id="provider-request-1",
            reasoning_content="private reasoning must not enter the result",
            tool_calls=(
                ModelToolCall(
                    id="tool-call-1",
                    name=self.tool_name,
                    arguments={
                        "public_analysis": (
                            "当前执行星历计算以核对观测时段，并以版本化结果和来源快照作为完成依据。"
                        )
                    },
                ),
            ),
        )


def test_agent_selects_exact_task_owned_scientific_skill() -> None:
    model = _Model("run_ephemeris")
    agent = ResearchStepAgent(
        model_port=model,
        provider="qwen",
        model="qwen-plus",
        model_revision="qwen-plus-2026-07-28",
        prompt=PromptRegistry().get("research_step_agent"),
    )
    prepared = agent.prepare_selection(
        step_key="scientific.abc",
        task_id="task.ephemeris",
        skill_id=ScientificSkillId.ephemeris,
        contract={"research_goal": "计算星历"},
        skill_revision="1.0.0",
    )
    decision = agent.execute_selection(prepared)
    result = agent.run(
        step_key="scientific.abc",
        task_id="task.ephemeris",
        skill_id=ScientificSkillId.ephemeris,
        contract={"research_goal": "计算星历"},
        skill_revision="1.0.0",
        execute_primary=lambda: {"status": "completed"},
    )

    assert result.value == {"status": "completed"}
    assert result.public_analysis.startswith("当前执行星历计算")
    assert prepared.authorized_tool_name == "run_ephemeris"
    assert prepared.authorized_skill_id == "ephemeris"
    assert prepared.registry_revision.startswith("sha256:")
    assert decision.output_hash == "sha256:" + "a" * 64
    assert decision.validated_arguments_hash == compute_canonical_payload_hash(
        {
            "public_analysis": (
                "当前执行星历计算以核对观测时段，并以版本化结果和来源快照作为完成依据。"
            )
        }
    )
    assert decision.token_usage == {
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "total_tokens": 14,
    }
    assert decision.latency_ms == 3
    request = model.requests[0]
    assert request.response_mode == "tool"
    assert request.enable_thinking is False
    assert request.tools[0]["function"]["name"] == "run_ephemeris"
    assert request.input_hash.startswith("sha256:")


def test_agent_rejects_unregistered_tool_without_executing_primary() -> None:
    executed = False

    def execute() -> object:
        nonlocal executed
        executed = True
        return object()

    model = _Model("shell")
    try:
        ResearchStepAgent(
            model_port=model,
            provider="qwen",
            model="qwen-plus",
            model_revision="qwen-plus-2026-07-28",
            prompt=PromptRegistry().get("research_step_agent"),
        ).run(
            step_key="scientific.abc",
            task_id="task.ephemeris",
            skill_id=ScientificSkillId.ephemeris,
            contract={"research_goal": "计算星历"},
            skill_revision="1.0.0",
            execute_primary=execute,
        )
    except AgentSelectionValidationError as exc:
        assert exc.code == "AGENT_TOOL_NOT_AUTHORIZED"
        assert exc.response.provider_request_id == "provider-request-1"
        assert exc.response.output_hash == "sha256:" + "a" * 64
        assert exc.tool_call_id == "tool-call-1"
        assert exc.rejected_arguments_hash == compute_canonical_payload_hash(
            exc.response.tool_calls[0].arguments
        )
    else:  # pragma: no cover - assertion guard
        raise AssertionError("unregistered tool must be rejected")
    assert executed is False


def test_rejected_call_audit_omits_ambiguous_or_unbounded_identity() -> None:
    call = ModelToolCall(id="call-1", name="shell", arguments={"secret": "value"})
    responses = (
        ModelExecutionResponse(
            payload={},
            output_hash="sha256:" + "b" * 64,
            token_usage=None,
            latency_ms=1,
            provider_request_id=None,
            tool_calls=(),
        ),
        ModelExecutionResponse(
            payload={},
            output_hash="sha256:" + "b" * 64,
            token_usage=None,
            latency_ms=1,
            provider_request_id=None,
            tool_calls=(call, call),
        ),
        ModelExecutionResponse(
            payload={},
            output_hash="sha256:" + "b" * 64,
            token_usage=None,
            latency_ms=1,
            provider_request_id=None,
            tool_calls=(
                ModelToolCall(id="x" * 257, name="shell", arguments={"secret": "value"}),
            ),
        ),
    )

    for response in responses:
        error = AgentSelectionValidationError(
            "AGENT_TOOL_CALL_COUNT_INVALID", response
        )
        assert error.tool_call_id is None
        assert error.rejected_arguments_hash is None


def test_agent_registry_revision_tracks_authority_not_contract_content() -> None:
    agent = ResearchStepAgent(
        model_port=_Model("run_ephemeris"),
        provider="qwen",
        model="qwen-plus",
        model_revision="qwen-plus-2026-07-28",
        prompt=PromptRegistry().get("research_step_agent"),
    )
    first = agent.prepare_selection(
        step_key="scientific.abc",
        task_id="task.ephemeris",
        skill_id=ScientificSkillId.ephemeris,
        contract={"research_goal": "计算星历"},
        skill_revision="1.0.0",
    )
    other_contract = agent.prepare_selection(
        step_key="scientific.abc",
        task_id="task.ephemeris",
        skill_id=ScientificSkillId.ephemeris,
        contract={"research_goal": "计算火星星历"},
        skill_revision="1.0.0",
    )
    upgraded_skill = agent.prepare_selection(
        step_key="scientific.abc",
        task_id="task.ephemeris",
        skill_id=ScientificSkillId.ephemeris,
        contract={"research_goal": "计算星历"},
        skill_revision="2.0.0",
    )

    assert first.registry_revision == other_contract.registry_revision
    assert first.model_request.input_hash != other_contract.model_request.input_hash
    assert first.registry_revision != upgraded_skill.registry_revision
