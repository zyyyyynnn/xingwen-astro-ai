"""Model-driven step runtime over a frozen, server-owned research tool registry."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Generic, TypeVar

from app.services.model_execution import (
    ModelExecutionPort,
    ModelExecutionRequest,
    ModelExecutionResponse,
    ModelToolCall,
)
from packages.prompts.registry import PromptRecord


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class AgentActivity:
    activity_id: str
    activity_kind: str
    activity_phase: str
    activity_name: str
    content: str
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AgentStepResult(Generic[T]):
    value: T
    activity_id: str
    activity_name: str
    activity_result_summary: str
    assistant_narrative: str


class AgentActivityError(RuntimeError):
    """Preserve the active public Activity identity across workflow failure handling."""

    def __init__(
        self,
        *,
        activity_id: str,
        activity_kind: str,
        activity_name: str,
        cause: Exception,
    ) -> None:
        super().__init__(str(cause))
        self.activity_id = activity_id
        self.activity_kind = activity_kind
        self.activity_name = activity_name
        self.cause = cause
        self.__cause__ = cause


@dataclass(frozen=True, slots=True)
class StepTool:
    name: str
    label: str
    tool_kind: str
    description: str

    @property
    def schema(self) -> dict[str, Any]:
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
                                "面向研究用户的简体中文步骤分析：说明本步骤为何现在执行、"
                                "将检查什么，以及如何判断该步骤完成。只描述执行前的判断，"
                                "不得描述尚未发生的执行结果，不得输出私有思维链。"
                            ),
                        },
                    },
                    "required": ["public_analysis"],
                    "additionalProperties": False,
                },
            },
        }


STEP_TOOLS: dict[str, StepTool] = {
    "planning": StepTool(
        "plan_research_path",
        "规划研究路径",
        "analysis",
        "根据已确认研究协议核对当前步骤的执行边界与依赖。",
    ),
    "fetching_data": StepTool(
        "query_astronomy_data",
        "查询天文数据",
        "data_query",
        "从研究协议允许的实时天文数据源查询研究对象。",
    ),
    "cleaning_data": StepTool(
        "validate_research_data",
        "整理并校验研究数据",
        "evidence_validation",
        "标准化字段与单位并执行数据质量校验。",
    ),
    "searching_papers": StepTool(
        "search_research_papers",
        "检索研究论文",
        "search",
        "按研究协议限定的主题与来源检索论文。",
    ),
    "summarizing_papers": StepTool(
        "read_research_paper",
        "阅读并归纳论文",
        "document_read",
        "读取已选论文并生成可追溯的结构化摘要。",
    ),
    "reasoning_literature": StepTool(
        "validate_literature_evidence",
        "分析并验证文献证据",
        "evidence_validation",
        "提取论点、比较关系并验证证据绑定。",
    ),
    "building_graph": StepTool(
        "build_evidence_graph",
        "生成证据图谱",
        "artifact_generation",
        "将已通过校验的论点与关系生成证据图谱。",
    ),
}

PUBLIC_ANALYSIS_INSTRUCTION = (
    "只调用当前提供的唯一工具，并在该次调用中通过 public_analysis 参数给出面向研究用户的"
    "简体中文执行前分析。public_analysis 必须从第一句开始使用简体中文，简洁说明本步骤"
    "为何现在执行、将检查什么以及如何判断该步骤完成。只描述执行前的判断，不得预测或描述"
    "尚未发生的执行结果；不得输出私有思维链，不得使用英文标题或分段，不得包含内部标识符、"
    "哈希或技术字段名。不可翻译的论文标题、模型字段、工具名与标准技术术语除外。"
)



class ResearchStepAgent:
    """Let Qwen explain and select one server-owned step capability."""

    def __init__(
        self,
        *,
        model_port: ModelExecutionPort,
        provider: str,
        requested_model: str,
        explicit_revision: str | None,
        prompt: PromptRecord,
        emit: Callable[[AgentActivity], None],
    ) -> None:
        self._model_port = model_port
        self._provider = provider
        self._requested_model = requested_model
        self._explicit_revision = explicit_revision
        self._prompt = prompt
        self._emit = emit

    def run(
        self,
        *,
        step_key: str,
        attempt_id: str,
        contract: dict[str, Any],
        available_artifacts: dict[str, str],
        execute_primary: Callable[[], T],
        describe_primary_result: Callable[[T], str],
        tool: StepTool | None = None,
    ) -> AgentStepResult[T]:
        primary = tool or STEP_TOOLS[step_key]
        task = {
            "step_key": step_key,
            "step_goal": primary.label,
            "research_contract": contract,
            "available_artifacts": available_artifacts,
        }
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._prompt.content},
            {
                "role": "user",
                "content": (
                    f"{PUBLIC_ANALYSIS_INSTRUCTION}\n\n"
                    f"当前研究任务：\n"
                    f"{json.dumps(task, ensure_ascii=False, sort_keys=True)}"
                ),
            },
        ]
        analysis_activity_id = f"{attempt_id}:analysis"
        self._emit(
            AgentActivity(
                activity_id=analysis_activity_id,
                activity_kind="reasoning",
                activity_phase="running",
                activity_name="分析",
                content=f"正在分析“{primary.label}”的执行条件与完成依据。",
                details={"analysis_type": "public"},
            )
        )
        try:
            response = self._model_port.execute(
                ModelExecutionRequest(
                    provider=self._provider,
                    requested_model=self._requested_model,
                    explicit_revision=self._explicit_revision,
                    prompt_name=self._prompt.name,
                    prompt_version=self._prompt.version,
                    prompt_hash=self._prompt.content_hash,
                    prompt=self._prompt.content,
                    input_payload={"step_key": step_key},
                    parameters={"temperature": 0.6, "top_p": 0.8},
                    conversation=tuple(messages),
                    tools=(primary.schema,),
                    response_mode="tool",
                    enable_thinking=False,
                ),
            )
            call = _single_tool_call(response)
            if call.name != primary.name:
                raise ValueError(f"Agent requested an unregistered tool: {call.name}")
            public_analysis = _public_analysis(call)
        except Exception as error:
            raise AgentActivityError(
                activity_id=analysis_activity_id,
                activity_kind="reasoning",
                activity_name="分析",
                cause=error,
            ) from error
        self._emit(
            AgentActivity(
                activity_id=analysis_activity_id,
                activity_kind="reasoning",
                activity_phase="completed",
                activity_name="分析",
                content=public_analysis,
                details={"analysis_type": "public"},
            )
        )
        self._emit(
            AgentActivity(
                activity_id=call.id,
                activity_kind="tool",
                activity_phase="running",
                activity_name=primary.label,
                content=f"正在{primary.label}。",
                details={
                    "tool_name": call.name,
                    "tool_kind": primary.tool_kind,
                },
            )
        )
        try:
            prepared = execute_primary()
        except Exception as error:
            raise AgentActivityError(
                activity_id=call.id,
                activity_kind="observation",
                activity_name=primary.label,
                cause=error,
            ) from error
        result_summary = describe_primary_result(prepared)
        observation = {"status": "completed", "summary": result_summary}
        self._emit(
            AgentActivity(
                activity_id=call.id,
                activity_kind="observation",
                activity_phase="completed",
                activity_name=primary.label,
                content=result_summary,
                details={
                    "tool_name": call.name,
                    "tool_kind": primary.tool_kind,
                    "result": observation,
                },
            )
        )
        assistant_narrative = deterministic_assistant_narrative(
            primary.label, result_summary
        )
        return AgentStepResult(
            value=prepared,
            activity_id=call.id,
            activity_name=primary.label,
            activity_result_summary=result_summary,
            assistant_narrative=assistant_narrative,
        )



def _single_tool_call(response: ModelExecutionResponse) -> ModelToolCall:
    if len(response.tool_calls) != 1:
        raise ValueError("Agent must select exactly one registered tool per turn")
    return response.tool_calls[0]


def _public_analysis(call: ModelToolCall) -> str:
    if set(call.arguments) != {"public_analysis"}:
        raise ValueError(f"Tool {call.name} requires only public_analysis")
    return _simplified_chinese_text(
        call.arguments["public_analysis"], call.name, "public_analysis"
    )




def deterministic_assistant_narrative(
    activity_name: str, activity_result_summary: str
) -> str:
    """Fallback Assistant Message for a completed, non-model explanation."""

    return f"“{activity_name}”已完成。{activity_result_summary}"




def _simplified_chinese_text(value: Any, tool_name: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Tool {tool_name} {field} must be non-empty text")
    text = value.strip()
    if not any("\u4e00" <= character <= "\u9fff" for character in text):
        raise ValueError(f"Tool {tool_name} {field} must use Simplified Chinese")
    return text


__all__ = [
    "AgentActivityError",
    "AgentActivity",
    "AgentStepResult",
    "ResearchStepAgent",
    "STEP_TOOLS",
    "deterministic_assistant_narrative",
]
