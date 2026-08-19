from __future__ import annotations

from uuid import UUID, uuid4

from app.services.model_execution import (
    ModelExecutionRequest,
    ModelExecutionResponse,
    ModelToolCall,
)
from app.workflow.agent_runtime import (
    AgentActivity,
    AgentActivityError,
    ResearchStepAgent,
)
from packages.prompts.registry import PromptRegistry


class ScriptedModel:
    def __init__(self) -> None:
        self.calls = 0
        self.requests: list[ModelExecutionRequest] = []

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        self.calls += 1
        self.requests.append(request)
        if request.response_mode == "json":
            return ModelExecutionResponse(
                payload={
                    "assistant_message": "查询结果已经纳入研究，后续步骤会继续使用这些数据。"
                },
                output_hash="sha256:" + "c" * 64,
                token_usage=None,
                latency_ms=1,
                provider_request_id=f"request-{self.calls}",
            )
        call = (
            ModelToolCall(
                "tool-1",
                "query_astronomy_data",
                {
                    "public_analysis": (
                        "研究协议已限定 NASA Exoplanet Archive，当前先查询宿主星参数，"
                        "并以返回记录及字段完整性作为完成依据。"
                    ),
                },
            )
            if self.calls == 1
            else ModelToolCall(
                "tool-2",
                "finish_step",
                {
                    "public_analysis": "当前步骤已有可用结果，可以结束执行。",
                },
            )
        )
        return ModelExecutionResponse(
            payload={},
            output_hash="sha256:" + "a" * 64,
            token_usage=None,
            latency_ms=1,
            provider_request_id=f"request-{self.calls}",
            tool_calls=(call,),
        )


class ScriptedAuditPort:
    """AgentAuditPort double recording the governed function-call lifecycle."""

    def __init__(self, model: ScriptedModel) -> None:
        self._model = model
        self.authorization: dict[str, str] | None = None
        self.completed: dict[str, object] | None = None
        self.rejected: dict[str, object] | None = None
        self.execution_id = uuid4()

    def start_agent_call(
        self,
        request: ModelExecutionRequest,
        *,
        authorized_tool_name: str,
        authorized_skill_id: str,
        registry_revision: str,
    ) -> tuple[ModelExecutionResponse, UUID]:
        self.authorization = {
            "authorized_tool_name": authorized_tool_name,
            "authorized_skill_id": authorized_skill_id,
            "registry_revision": registry_revision,
        }
        return self._model.execute(request), self.execution_id

    def complete_agent_call(
        self,
        execution_id: UUID,
        *,
        response: ModelExecutionResponse,
        tool_call_id: str,
        validated_arguments_hash: str,
        public_message: str,
    ) -> None:
        assert execution_id == self.execution_id
        self.completed = {
            "tool_call_id": tool_call_id,
            "validated_arguments_hash": validated_arguments_hash,
            "public_message": public_message,
        }

    def reject_agent_call(
        self,
        execution_id: UUID,
        *,
        error_code: str,
        error_hash: str,
        response: ModelExecutionResponse | None = None,
        tool_call_id: str | None = None,
        rejected_arguments_hash: str | None = None,
    ) -> None:
        assert execution_id == self.execution_id
        self.rejected = {
            "error_code": error_code,
            "error_hash": error_hash,
            "tool_call_id": tool_call_id,
            "rejected_arguments_hash": rejected_arguments_hash,
        }


def test_agent_emits_reasoning_and_one_tool_lifecycle() -> None:
    emitted: list[AgentActivity] = []
    model = ScriptedModel()
    audit = ScriptedAuditPort(model)
    agent = ResearchStepAgent(
        model_port=audit,
        provider="qwen",
        requested_model="qwen3.8-max",
        explicit_revision="",
        prompt=PromptRegistry().get("research_step_agent"),
        emit=emitted.append,
    )

    result = agent.run(
        step_key="fetching_data",
        attempt_id="attempt-1",
        contract={"research_goal": "查询宿主星参数"},
        available_artifacts={},
        execute_primary=lambda: {"rows": 2},
        describe_primary_result=lambda value: f"已获取 {value['rows']} 条记录。",
    )

    assert result.value == {"rows": 2}
    assert result.activity_id == "tool-1"
    assert result.activity_result_summary == "已获取 2 条记录。"
    assert result.assistant_narrative == (
        "“查询天文数据”已完成。已获取 2 条记录。"
    )
    assert [activity.activity_kind for activity in emitted] == [
        "reasoning",
        "reasoning",
        "tool",
        "observation",
    ]
    assert emitted[0].activity_phase == "running"
    assert emitted[1].activity_id == emitted[0].activity_id
    assert emitted[1].activity_phase == "completed"
    assert emitted[1].content.startswith("研究协议已限定")
    assert emitted[2].activity_phase == "running"
    assert emitted[3].activity_id == emitted[2].activity_id
    assert emitted[3].activity_phase == "completed"
    assert emitted[3].content == "已获取 2 条记录。"

    request = model.requests[0]
    user_message = request.conversation[1]["content"]
    assert isinstance(user_message, str)
    assert user_message.startswith("只调用当前提供的唯一工具")
    assert "public_analysis 必须从第一句开始使用简体中文" in user_message
    assert '"step_key": "fetching_data"' in user_message
    assert request.enable_thinking is False
    tool_parameters = request.tools[0]["function"]["parameters"]
    assert tool_parameters["required"] == ["public_analysis"]
    assert set(tool_parameters["properties"]) == {"public_analysis"}
    assert audit.authorization == {
        "authorized_tool_name": "query_astronomy_data",
        "authorized_skill_id": "fetching_data",
        "registry_revision": "research_step_tools.v1",
    }
    assert audit.completed is not None
    assert audit.completed["tool_call_id"] == "tool-1"
    assert audit.completed["validated_arguments_hash"].startswith("sha256:")
    assert audit.completed["public_message"].startswith("研究协议已限定")
    assert audit.rejected is None


def test_agent_does_not_require_a_second_model_call_after_tool_success() -> None:
    class SingleDecisionModel(ScriptedModel):
        def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
            if self.calls > 0:
                raise AssertionError("tool success must finish the server-owned step")
            return super().execute(request)

    model = SingleDecisionModel()
    agent = ResearchStepAgent(
        model_port=ScriptedAuditPort(model),
        provider="qwen",
        requested_model="qwen3.8-max",
        explicit_revision="",
        prompt=PromptRegistry().get("research_step_agent"),
        emit=lambda _activity: None,
    )

    result = agent.run(
        step_key="fetching_data",
        attempt_id="attempt-1",
        contract={"research_goal": "查询宿主星参数"},
        available_artifacts={},
        execute_primary=lambda: {"rows": 2},
        describe_primary_result=lambda value: f"已获取 {value['rows']} 条记录。",
    )

    assert result.value == {"rows": 2}
    assert result.assistant_narrative == (
        "“查询天文数据”已完成。已获取 2 条记录。"
    )
    assert model.calls == 1


def test_agent_rejects_an_unregistered_tool() -> None:
    class InvalidModel(ScriptedModel):
        def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
            return ModelExecutionResponse(
                payload={},
                output_hash="sha256:" + "b" * 64,
                token_usage=None,
                latency_ms=1,
                provider_request_id="request-invalid",
                tool_calls=(
                    ModelToolCall(
                        "tool-invalid",
                        "shell",
                        {
                            "public_analysis": "尝试调用未注册工具。",
                        },
                    ),
                ),
            )

    audit = ScriptedAuditPort(InvalidModel())
    agent = ResearchStepAgent(
        model_port=audit,
        provider="qwen",
        requested_model="qwen3.8-max",
        explicit_revision="",
        prompt=PromptRegistry().get("research_step_agent"),
        emit=lambda _activity: None,
    )

    try:
        agent.run(
            step_key="fetching_data",
            attempt_id="attempt-1",
            contract={},
            available_artifacts={},
            execute_primary=lambda: {},
            describe_primary_result=lambda _value: "完成",
        )
    except AgentActivityError as exc:
        assert isinstance(exc.cause, ValueError)
        assert "unregistered tool" in str(exc.cause)
        assert exc.activity_kind == "reasoning"
        assert exc.activity_name == "分析"
    else:  # pragma: no cover - assertion guard
        raise AssertionError("unregistered tool must be rejected")
    assert audit.completed is None
    assert audit.rejected is not None
    assert audit.rejected["error_code"] == "AGENT_TOOL_CALL_REJECTED"
    assert audit.rejected["tool_call_id"] == "tool-invalid"
    assert audit.rejected["rejected_arguments_hash"].startswith("sha256:")
    assert audit.rejected["error_hash"].startswith("sha256:")


def test_agent_preserves_tool_activity_identity_when_execution_fails() -> None:
    emitted: list[AgentActivity] = []
    agent = ResearchStepAgent(
        model_port=ScriptedAuditPort(ScriptedModel()),
        provider="qwen",
        requested_model="qwen3.8-max",
        explicit_revision="",
        prompt=PromptRegistry().get("research_step_agent"),
        emit=emitted.append,
    )

    def fail_primary() -> dict[str, int]:
        raise RuntimeError("private adapter detail")

    try:
        agent.run(
            step_key="fetching_data",
            attempt_id="attempt-1",
            contract={},
            available_artifacts={},
            execute_primary=fail_primary,
            describe_primary_result=lambda _value: "完成",
        )
    except AgentActivityError as exc:
        assert exc.activity_id == "tool-1"
        assert exc.activity_kind == "observation"
        assert exc.activity_name == "查询天文数据"
        assert isinstance(exc.cause, RuntimeError)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("tool execution failure must preserve Activity identity")

    assert emitted[-1].activity_id == "tool-1"
    assert emitted[-1].activity_phase == "running"
