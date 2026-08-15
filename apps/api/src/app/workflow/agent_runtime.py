"""Model-driven selection of one frozen, server-owned Workflow capability."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable, Generic, TypeVar

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ScientificSkillId
from app.services.model_execution import (
    ModelExecutionPort,
    ModelExecutionRequest,
    ModelExecutionResponse,
    ModelToolCall,
)
from packages.prompts.registry import PromptRecord


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class AgentStepResult(Generic[T]):
    value: T
    public_analysis: str
    tool_call_id: str
    provider_request_id: str | None
    output_hash: str
    validated_arguments_hash: str
    token_usage: dict[str, int] | None
    latency_ms: int


@dataclass(frozen=True, slots=True)
class AgentDecision:
    public_analysis: str
    tool_call_id: str
    provider_request_id: str | None
    output_hash: str
    validated_arguments_hash: str
    token_usage: dict[str, int] | None
    latency_ms: int
    authorized_tool_name: str
    authorized_skill_id: str | None
    registry_revision: str


@dataclass(frozen=True, slots=True)
class PreparedAgentSelection:
    model_request: ModelExecutionRequest
    authorized_tool_name: str
    authorized_skill_id: str | None
    registry_revision: str


class AgentSelectionValidationError(ValueError):
    """A provider response that cannot authorize the frozen server capability."""

    def __init__(self, code: str, response: ModelExecutionResponse) -> None:
        super().__init__("研究助手未返回可执行的受控步骤。")
        self.code = code
        self.public_message = "研究助手未返回可执行的受控步骤。"
        self.response = response
        self.tool_call_id, self.rejected_arguments_hash = _rejected_call_audit(
            response
        )


@dataclass(frozen=True, slots=True)
class StepTool:
    name: str
    label: str
    description: str
    revision: str = "1.0.0"

    @property
    def schema(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "public_analysis": {
                            "type": "string",
                            "minLength": 12,
                            "maxLength": 500,
                            "description": (
                                "面向研究用户的简体中文步骤分析；说明为何执行、核对内容和"
                                "完成依据，不得输出私有思维链。"
                            ),
                        }
                    },
                    "required": ["public_analysis"],
                    "additionalProperties": False,
                },
            },
        }


_FIXED_STEP_TOOLS = {
    "planning": StepTool(
        "confirm_research_plan",
        "确认研究计划",
        "核对已确认研究协议、步骤依赖和执行边界。",
    ),
    "fetching_data": StepTool(
        "query_astronomy_data",
        "查询天文数据",
        "从研究协议允许的实时天文数据源查询研究对象。",
    ),
    "cleaning_data": StepTool(
        "validate_research_data",
        "整理并校验研究数据",
        "标准化字段与单位并执行数据质量校验。",
    ),
    "searching_papers": StepTool(
        "search_research_papers",
        "检索研究论文",
        "按研究协议限定的主题与来源检索论文。",
    ),
    "summarizing_papers": StepTool(
        "read_research_paper",
        "阅读并归纳论文",
        "读取已选论文并生成可追溯的结构化摘要。",
    ),
    "reasoning_literature": StepTool(
        "validate_literature_evidence",
        "分析并验证文献证据",
        "提取论点、比较关系并验证证据绑定。",
    ),
    "building_graph": StepTool(
        "build_evidence_graph",
        "生成证据图谱",
        "将已通过校验的论点与关系生成证据图谱。",
    ),
}


class ResearchStepAgent:
    """Select exactly one bounded capability, then let the server execute it."""

    def __init__(
        self,
        *,
        model_port: ModelExecutionPort,
        provider: str,
        model: str,
        model_revision: str,
        prompt: PromptRecord,
    ) -> None:
        self._model_port = model_port
        self._provider = provider
        self._model = model
        self._model_revision = model_revision
        self._prompt = prompt

    def run(
        self,
        *,
        step_key: str,
        task_id: str | None,
        skill_id: ScientificSkillId | None,
        contract: dict[str, object],
        skill_revision: str | None = None,
        execute_primary: Callable[[], T],
    ) -> AgentStepResult[T]:
        decision = self.select(
            step_key=step_key,
            task_id=task_id,
            skill_id=skill_id,
            contract=contract,
            skill_revision=skill_revision,
        )
        return AgentStepResult(
            value=execute_primary(),
            public_analysis=decision.public_analysis,
            tool_call_id=decision.tool_call_id,
            provider_request_id=decision.provider_request_id,
            output_hash=decision.output_hash,
            validated_arguments_hash=decision.validated_arguments_hash,
            token_usage=decision.token_usage,
            latency_ms=decision.latency_ms,
        )

    def select(
        self,
        *,
        step_key: str,
        task_id: str | None,
        skill_id: ScientificSkillId | None,
        contract: dict[str, object],
        skill_revision: str | None = None,
    ) -> AgentDecision:
        """Validate one model tool selection without executing the capability."""

        return self.execute_selection(
            self.prepare_selection(
                step_key=step_key,
                task_id=task_id,
                skill_id=skill_id,
                contract=contract,
                skill_revision=skill_revision,
            )
        )

    def prepare_selection(
        self,
        *,
        step_key: str,
        task_id: str | None,
        skill_id: ScientificSkillId | None,
        contract: dict[str, object],
        skill_revision: str | None = None,
    ) -> PreparedAgentSelection:
        """Freeze the exact provider request and server authorization identity."""

        tool = _tool_for(step_key=step_key, task_id=task_id, skill_id=skill_id)
        if skill_id is not None and not (skill_revision or "").strip():
            raise ValueError("scientific skill revision is required")
        if skill_id is None and skill_revision is not None:
            raise ValueError(
                "fixed Workflow capability cannot declare a skill revision"
            )
        authorized_skill_id = skill_id.value if skill_id is not None else None
        authorized_revision = skill_revision or tool.revision
        task = {
            "step_key": step_key,
            "task_id": task_id,
            "skill_id": skill_id.value if skill_id is not None else None,
            "step_goal": tool.label,
            "research_contract": contract,
        }
        model_request = ModelExecutionRequest(
            provider=self._provider,
            model=self._model,
            model_revision=self._model_revision,
            prompt_name=self._prompt.name,
            prompt_version=self._prompt.version,
            prompt_hash=self._prompt.content_hash,
            prompt=self._prompt.content,
            input_payload=task,
            parameters={"temperature": 0.2, "top_p": 0.8},
            conversation=(
                {"role": "system", "content": self._prompt.content},
                {
                    "role": "user",
                    "content": (
                        "只调用当前提供的唯一工具。通过 public_analysis 用简体中文说明"
                        "执行原因、核对内容和完成依据；不得输出私有思维链。\n\n"
                        + json.dumps(task, ensure_ascii=False, sort_keys=True)
                    ),
                },
            ),
            tools=(tool.schema,),
            response_mode="tool",
            enable_thinking=False,
            stream=False,
        )
        registry_revision = compute_canonical_payload_hash(
            {
                "authorized_tool": tool.schema,
                "authorized_skill_id": authorized_skill_id,
                "authorized_revision": authorized_revision,
            }
        )
        return PreparedAgentSelection(
            model_request=model_request,
            authorized_tool_name=tool.name,
            authorized_skill_id=authorized_skill_id,
            registry_revision=registry_revision,
        )

    def execute_selection(self, prepared: PreparedAgentSelection) -> AgentDecision:
        """Execute and validate one prepared Function Calling request."""

        response = self._model_port.execute(prepared.model_request)
        try:
            call = _single_tool_call(response)
        except ValueError as exc:
            raise AgentSelectionValidationError(
                "AGENT_TOOL_CALL_COUNT_INVALID", response
            ) from exc
        if call.name != prepared.authorized_tool_name:
            raise AgentSelectionValidationError("AGENT_TOOL_NOT_AUTHORIZED", response)
        try:
            public_analysis = _public_analysis(call)
        except ValueError as exc:
            raise AgentSelectionValidationError(
                "AGENT_ARGUMENTS_INVALID", response
            ) from exc
        return AgentDecision(
            public_analysis=public_analysis,
            tool_call_id=call.id,
            provider_request_id=response.provider_request_id,
            output_hash=response.output_hash,
            validated_arguments_hash=compute_canonical_payload_hash(call.arguments),
            token_usage=(dict(response.token_usage) if response.token_usage else None),
            latency_ms=response.latency_ms,
            authorized_tool_name=prepared.authorized_tool_name,
            authorized_skill_id=prepared.authorized_skill_id,
            registry_revision=prepared.registry_revision,
        )


def _tool_for(
    *,
    step_key: str,
    task_id: str | None,
    skill_id: ScientificSkillId | None,
) -> StepTool:
    if skill_id is not None:
        if task_id is None or not step_key.startswith("scientific."):
            raise ValueError("scientific RunStep binding is incomplete")
        return StepTool(
            name=f"run_{skill_id.value}",
            label=f"执行 {skill_id.value}",
            description=(
                f"执行研究协议已授权的 {skill_id.value} ScientificSkill，"
                f"任务标识为 {task_id}。"
            ),
        )
    try:
        return _FIXED_STEP_TOOLS[step_key]
    except KeyError as exc:
        raise ValueError(f"RunStep has no registered capability: {step_key}") from exc


def _single_tool_call(response: ModelExecutionResponse) -> ModelToolCall:
    if len(response.tool_calls) != 1:
        raise ValueError("Agent must select exactly one registered tool")
    return response.tool_calls[0]


def _rejected_call_audit(
    response: ModelExecutionResponse,
) -> tuple[str | None, str | None]:
    """Return bounded identity and hash-only arguments for one rejected call."""

    if len(response.tool_calls) != 1:
        return None, None
    call = response.tool_calls[0]
    if not isinstance(call.id, str):
        return None, None
    call_id = call.id.strip()
    if not call_id or len(call_id) > 256:
        return None, None
    return call_id, compute_canonical_payload_hash(call.arguments)


def _public_analysis(call: ModelToolCall) -> str:
    if set(call.arguments) != {"public_analysis"}:
        raise ValueError(f"Tool {call.name} requires only public_analysis")
    value = call.arguments["public_analysis"]
    if not isinstance(value, str):
        raise ValueError(f"Tool {call.name} public_analysis must be text")
    analysis = value.strip()
    if len(analysis) < 12 or len(analysis) > 500:
        raise ValueError(f"Tool {call.name} public_analysis is outside bounds")
    if not any("\u4e00" <= character <= "\u9fff" for character in analysis):
        raise ValueError(f"Tool {call.name} public_analysis must use Chinese")
    return analysis


__all__ = [
    "AgentDecision",
    "AgentSelectionValidationError",
    "AgentStepResult",
    "PreparedAgentSelection",
    "ResearchStepAgent",
    "StepTool",
]
