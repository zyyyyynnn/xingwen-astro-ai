"""Provider-neutral model execution boundary and the pinned Qwen adapter."""

from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import timedelta
from time import monotonic
from typing import Any, Callable, Literal, Protocol, cast

from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, OpenAI

from app.security import canonical_request_hash


# OpenAI's compatible client honors each provider Retry-After value up to two
# minutes. The dependency is pinned, and the lease calculation reserves that
# complete worst-case wait for every configured retry.
QWEN_MAX_RETRY_DELAY_SECONDS = 120.0
_QWEN_ALLOWED_PARAMETERS = frozenset(
    {
        "frequency_penalty",
        "max_output_tokens",
        "max_tokens",
        "presence_penalty",
        "seed",
        "stop",
        "temperature",
        "top_p",
    }
)
_QWEN_TRANSPORT_OWNED_PARAMETERS = frozenset(
    {
        "extra_body",
        "messages",
        "model",
        "response_format",
        "stream",
        "tool_choice",
        "tools",
    }
)


def qwen_execution_lease_duration(
    *, timeout_seconds: float, max_retries: int, grace_seconds: float
) -> timedelta:
    if timeout_seconds <= 0 or grace_seconds <= 0 or max_retries < 0:
        raise ValueError("Qwen execution timing values must be positive")
    return timedelta(
        seconds=(
            timeout_seconds * (max_retries + 1)
            + QWEN_MAX_RETRY_DELAY_SECONDS * max_retries
            + grace_seconds
        )
    )


@dataclass(frozen=True, slots=True)
class ModelExecutionRequest:
    provider: str
    model: str
    model_revision: str
    prompt_name: str
    prompt_version: str
    prompt_hash: str
    prompt: str
    input_payload: dict[str, Any]
    parameters: dict[str, Any]
    conversation: tuple[dict[str, Any], ...] = ()
    tools: tuple[dict[str, Any], ...] = ()
    response_mode: Literal["json", "tool"] = "json"
    enable_thinking: bool = False
    stream: bool = False

    @property
    def input_hash(self) -> str:
        return canonical_request_hash(self.input_payload)

    @property
    def parameters_hash(self) -> str:
        return canonical_request_hash(self.parameters)


@dataclass(frozen=True, slots=True)
class ModelExecutionResponse:
    payload: dict[str, Any]
    output_hash: str
    token_usage: dict[str, int] | None
    latency_ms: int
    provider_request_id: str | None
    reasoning_content: str | None = None
    assistant_content: str | None = None
    tool_calls: tuple[ModelToolCall, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


class ModelExecutionPort(Protocol):
    def execute(
        self,
        request: ModelExecutionRequest,
        *,
        on_reasoning_delta: Callable[[str], None] | None = None,
    ) -> ModelExecutionResponse:
        """Execute one typed, hash-identifiable model request."""


class ModelExecutionError(RuntimeError):
    """Safe failure plus any provider execution metadata already observed."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        output_hash: str | None = None,
        token_usage: dict[str, int] | None = None,
        latency_ms: int | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.output_hash = output_hash
        self.token_usage = token_usage
        self.latency_ms = latency_ms
        self.provider_request_id = provider_request_id


class ModelRuntimeUnavailable(ModelExecutionError):
    def __init__(
        self,
        *,
        latency_ms: int | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        super().__init__(
            "MODEL_RUNTIME_UNAVAILABLE",
            "研究助手暂时不可用，请稍后重试。",
            latency_ms=latency_ms,
            provider_request_id=provider_request_id,
        )


class QwenModelExecutionAdapter:
    """Thin Qwen adapter over the platform's OpenAI-compatible SDK route.

    The adapter owns transport mapping only. It does not validate planner
    semantics or persist provider payloads; callers must do both at the
    application boundary.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        timeout_seconds: float,
        max_retries: int = 2,
        client: OpenAI | None = None,
    ) -> None:
        self._api_key = api_key.strip() if api_key else None
        self._client = client
        if self._api_key and self._client is None:
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=base_url.rstrip("/"),
                timeout=timeout_seconds,
                max_retries=max_retries,
            )

    def execute(
        self,
        request: ModelExecutionRequest,
        *,
        on_reasoning_delta: Callable[[str], None] | None = None,
    ) -> ModelExecutionResponse:
        if not self._api_key:
            raise ModelRuntimeUnavailable()

        client = cast(OpenAI, self._client)
        transport_parameters = _qwen_transport_parameters(request.parameters)
        started = monotonic()
        messages = (
            list(request.conversation)
            if request.conversation
            else [
                {"role": "system", "content": request.prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        request.input_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                },
            ]
        )
        create_arguments: dict[str, Any] = {
            "model": request.model_revision,
            "messages": messages,
            "extra_body": {"enable_thinking": request.enable_thinking},
            **transport_parameters,
        }
        if request.enable_thinking:
            create_arguments["extra_body"]["preserve_thinking"] = True
        if request.response_mode == "json":
            create_arguments["response_format"] = {"type": "json_object"}
        elif not request.tools:
            raise ModelExecutionError(
                "MODEL_REQUEST_INVALID",
                "工具调用模式至少需要一个平台注册工具。",
            )
        if request.tools:
            if len(request.tools) > 16:
                raise ModelExecutionError(
                    "MODEL_REQUEST_INVALID",
                    "模型请求包含过多工具。",
                )
            create_arguments["tools"] = list(request.tools)
            create_arguments["tool_choice"] = "auto"
        if request.stream:
            create_arguments["stream"] = True
            create_arguments["stream_options"] = {"include_usage": True}
        try:
            completion = client.chat.completions.create(**create_arguments)
            raw = (
                _consume_stream(completion, on_reasoning_delta)
                if request.stream
                else _consume_completion(completion, on_reasoning_delta)
            )
        except APITimeoutError as exc:
            raise ModelExecutionError(
                "MODEL_PROVIDER_TIMEOUT",
                "研究助手响应超时，请稍后重试。",
                latency_ms=_elapsed_ms(started),
                provider_request_id=getattr(exc, "request_id", None),
            ) from exc
        except APIStatusError as exc:
            failure_metadata = {
                "latency_ms": _elapsed_ms(started),
                "provider_request_id": getattr(exc, "request_id", None),
            }
            provider_code = (
                exc.body.get("code")
                if isinstance(exc.body, dict)
                and isinstance(exc.body.get("code"), str)
                else None
            )
            if (
                exc.status_code == 403
                and provider_code == "AllocationQuota.FreeTierOnly"
            ):
                raise ModelExecutionError(
                    "MODEL_QUOTA_EXHAUSTED",
                    "研究助手调用额度已用尽，请联系管理员检查模型配额。",
                    **failure_metadata,
                ) from exc
            if exc.status_code == 429:
                raise ModelExecutionError(
                    "MODEL_RATE_LIMITED",
                    "研究助手当前请求较多，请稍后重试。",
                    **failure_metadata,
                ) from exc
            if exc.status_code >= 500:
                raise ModelExecutionError(
                    "MODEL_PROVIDER_UNAVAILABLE",
                    "研究助手服务暂时不可用，请稍后重试。",
                    **failure_metadata,
                ) from exc
            raise ModelExecutionError(
                "MODEL_PROVIDER_REJECTED",
                "研究助手未接受本次请求。",
                **failure_metadata,
            ) from exc
        except (APIConnectionError, APIError) as exc:
            raise ModelRuntimeUnavailable(
                latency_ms=_elapsed_ms(started),
                provider_request_id=getattr(exc, "request_id", None),
            ) from exc

        latency_ms = _elapsed_ms(started)
        try:
            payload = (
                _parse_json_content(raw.content)
                if request.response_mode == "json"
                else {}
            )
            tool_calls = tuple(_parse_tool_call(item) for item in raw.tool_calls)
        except (ValueError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ModelExecutionError(
                "MODEL_RESPONSE_INVALID",
                "研究助手返回了无法验证的结果。",
                output_hash=canonical_request_hash(
                    {
                        "provider_content": raw.content,
                        "tool_calls": raw.tool_calls,
                    }
                ),
                token_usage=raw.token_usage,
                latency_ms=latency_ms,
                provider_request_id=raw.provider_request_id,
            ) from exc

        output_projection = (
            payload
            if request.response_mode == "json"
            else {
                "content": raw.content,
                "reasoning_content": raw.reasoning_content,
                "tool_calls": [
                    {
                        "id": item.id,
                        "name": item.name,
                        "arguments": item.arguments,
                    }
                    for item in tool_calls
                ],
            }
        )
        return ModelExecutionResponse(
            payload=payload,
            output_hash=canonical_request_hash(output_projection),
            token_usage=raw.token_usage,
            latency_ms=latency_ms,
            provider_request_id=raw.provider_request_id,
            reasoning_content=raw.reasoning_content or None,
            assistant_content=raw.content or None,
            tool_calls=tool_calls,
        )


@dataclass(frozen=True, slots=True)
class _RawCompletion:
    content: str
    reasoning_content: str
    tool_calls: tuple[dict[str, str], ...]
    token_usage: dict[str, int] | None
    provider_request_id: str | None


def _consume_completion(
    completion: Any,  # noqa: ANN401
    on_reasoning_delta: Callable[[str], None] | None,
) -> _RawCompletion:
    message = completion.choices[0].message if completion.choices else None
    content = getattr(message, "content", None) or ""
    reasoning_content = getattr(message, "reasoning_content", None) or ""
    if reasoning_content and on_reasoning_delta is not None:
        on_reasoning_delta(reasoning_content)
    tool_calls = tuple(
        {
            "id": str(getattr(item, "id", "")),
            "name": str(getattr(getattr(item, "function", None), "name", "")),
            "arguments": str(
                getattr(getattr(item, "function", None), "arguments", "")
            ),
        }
        for item in (getattr(message, "tool_calls", None) or ())
    )
    return _RawCompletion(
        content=content,
        reasoning_content=reasoning_content,
        tool_calls=tool_calls,
        token_usage=_standard_token_usage(getattr(completion, "usage", None)),
        provider_request_id=(
            getattr(completion, "_request_id", None)
            or getattr(completion, "id", None)
        ),
    )


def _consume_stream(
    completion: Any,  # noqa: ANN401
    on_reasoning_delta: Callable[[str], None] | None,
) -> _RawCompletion:
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: dict[int, dict[str, str]] = {}
    token_usage: dict[str, int] | None = None
    provider_request_id: str | None = None
    for chunk in completion:
        provider_request_id = (
            getattr(chunk, "_request_id", None)
            or getattr(chunk, "id", None)
            or provider_request_id
        )
        if (usage := _standard_token_usage(getattr(chunk, "usage", None))) is not None:
            token_usage = usage
        if not getattr(chunk, "choices", None):
            continue
        delta = chunk.choices[0].delta
        if content := getattr(delta, "content", None):
            content_parts.append(content)
        if reasoning := getattr(delta, "reasoning_content", None):
            reasoning_parts.append(reasoning)
            if on_reasoning_delta is not None:
                on_reasoning_delta(reasoning)
        for item in getattr(delta, "tool_calls", None) or ():
            index = int(getattr(item, "index", 0))
            current = tool_calls.setdefault(
                index, {"id": "", "name": "", "arguments": ""}
            )
            if value := getattr(item, "id", None):
                current["id"] += value
            function = getattr(item, "function", None)
            if value := getattr(function, "name", None):
                current["name"] += value
            if value := getattr(function, "arguments", None):
                current["arguments"] += value
    return _RawCompletion(
        content="".join(content_parts),
        reasoning_content="".join(reasoning_parts),
        tool_calls=tuple(tool_calls[index] for index in sorted(tool_calls)),
        token_usage=token_usage,
        provider_request_id=provider_request_id,
    )


def _parse_tool_call(value: dict[str, str]) -> ModelToolCall:
    call_id = value["id"].strip()
    name = value["name"].strip()
    if not call_id or not name:
        raise ValueError("tool call identity is incomplete")
    parsed = json.loads(value["arguments"] or "{}")
    if not isinstance(parsed, dict):
        raise ValueError("tool call arguments must be a JSON object")
    return ModelToolCall(id=call_id, name=name, arguments=parsed)


def _standard_token_usage(usage: Any) -> dict[str, int] | None:  # noqa: ANN401
    if usage is None:
        return None
    payload = usage.model_dump(exclude_none=True)
    normalized = {
        key: value
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        if type(value := payload.get(key)) is int and value >= 0
    }
    return normalized or None


def _qwen_transport_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    keys = set(parameters)
    transport_owned = sorted(keys & _QWEN_TRANSPORT_OWNED_PARAMETERS)
    if transport_owned:
        raise ModelExecutionError(
            "MODEL_REQUEST_INVALID",
            "模型请求包含由平台管理的传输参数。",
        )
    unsupported = sorted(keys - _QWEN_ALLOWED_PARAMETERS)
    if unsupported:
        raise ModelExecutionError(
            "MODEL_REQUEST_INVALID",
            "模型请求包含不受支持的参数。",
        )
    if "max_tokens" in parameters and "max_output_tokens" in parameters:
        raise ModelExecutionError(
            "MODEL_REQUEST_INVALID",
            "模型请求包含冲突的输出长度参数。",
        )
    result = dict(parameters)
    if "max_output_tokens" in result:
        result["max_tokens"] = result.pop("max_output_tokens")
    return result


def _elapsed_ms(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))


def _parse_json_content(content: Any) -> dict[str, Any]:  # noqa: ANN401
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise ValueError("model content is not JSON text")
    text = content.strip()
    if text.startswith("```"):
        text = text.removeprefix("```").removeprefix("json").removesuffix("```").strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("model content must be a JSON object")
    return parsed


__all__ = [
    "ModelExecutionError",
    "ModelExecutionPort",
    "ModelExecutionRequest",
    "ModelExecutionResponse",
    "ModelToolCall",
    "ModelRuntimeUnavailable",
    "QwenModelExecutionAdapter",
    "qwen_execution_lease_duration",
]
