"""Provider-neutral model execution boundary and the pinned Qwen adapter."""

from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import timedelta
from time import monotonic
from typing import Any, Literal, Protocol, cast

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    DefaultHttpxClient,
    OpenAI,
)

from app.security import canonical_request_hash


# OpenAI's compatible client honors each provider Retry-After value up to two
# minutes. The dependency is pinned, and the lease calculation reserves that
# complete worst-case wait for every configured retry.
QWEN_MAX_RETRY_DELAY_SECONDS = 120.0


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
    requested_model: str
    explicit_revision: str | None
    prompt_name: str
    prompt_version: str
    prompt_hash: str
    prompt: str
    input_payload: dict[str, Any]
    parameters: dict[str, Any]
    conversation: tuple[dict[str, Any], ...] = ()
    tools: tuple[dict[str, Any], ...] = ()
    response_mode: Literal["json", "tool"] = "json"
    enable_thinking: bool = True

    @property
    def input_hash(self) -> str:
        return canonical_request_hash(self.input_payload)

    @property
    def parameters_hash(self) -> str:
        return canonical_request_hash(self.parameters)


@dataclass(frozen=True, slots=True)
class ModelToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ModelExecutionResponse:
    payload: dict[str, Any]
    output_hash: str
    token_usage: dict[str, int] | None
    latency_ms: int
    provider_request_id: str | None
    provider_returned_model: str | None = None
    tool_calls: tuple[ModelToolCall, ...] = ()


class ModelExecutionPort(Protocol):
    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
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


class OpenAICompatibleModelExecutionAdapter:
    """Thin adapter over the OpenAI Chat Completions compatible SDK route.

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
        qwen_thinking_control: bool = False,
    ) -> None:
        self._api_key = api_key.strip() if api_key else None
        self._client = client
        self._qwen_thinking_control = qwen_thinking_control
        if self._api_key and self._client is None:
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=base_url.rstrip("/"),
                timeout=timeout_seconds,
                max_retries=max_retries,
                http_client=DefaultHttpxClient(follow_redirects=False),
            )

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        if not self._api_key:
            raise ModelRuntimeUnavailable()

        client = cast(OpenAI, self._client)
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
            "model": request.explicit_revision or request.requested_model,
            "messages": messages,
            **request.parameters,
        }
        if self._qwen_thinking_control:
            create_arguments["extra_body"] = {
                "enable_thinking": request.enable_thinking,
                "preserve_thinking": request.enable_thinking,
            }
        if request.response_mode == "json":
            create_arguments["response_format"] = {"type": "json_object"}
        if request.tools:
            create_arguments["tools"] = list(request.tools)
            create_arguments["tool_choice"] = "auto"
        try:
            completion = client.chat.completions.create(**create_arguments)
            raw = _consume_completion(completion)
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
            provider_code = _provider_error_code(exc)
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
            if provider_code in {
                "access_denied",
                "AllocationQuota.FreeTierOnly",
            }:
                raise ModelExecutionError(
                    "MODEL_ACCESS_UNAVAILABLE",
                    "当前研究模型尚未开通或额度不足，请检查模型套餐后重试。",
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
        if raw.finish_reason == "length":
            raise ModelExecutionError(
                "MODEL_RESPONSE_TRUNCATED",
                "研究助手返回结果不完整，请稍后重试。",
                output_hash=canonical_request_hash({"provider_content": raw.content}),
                token_usage=raw.token_usage,
                latency_ms=latency_ms,
                provider_request_id=raw.provider_request_id,
            )
        if request.response_mode == "tool" and raw.finish_reason not in (
            None,
            "stop",
            "tool_calls",
        ):
            raise ModelExecutionError(
                "MODEL_RESPONSE_UNFINISHED",
                "研究助手未返回完整结果，请稍后重试。",
                output_hash=canonical_request_hash({"provider_content": raw.content}),
                token_usage=raw.token_usage,
                latency_ms=latency_ms,
                provider_request_id=raw.provider_request_id,
            )
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

        return ModelExecutionResponse(
            payload=payload,
            output_hash=canonical_request_hash(
                payload
                if request.response_mode == "json"
                else {
                    "content": raw.content,
                    "tool_calls": [
                        {
                            "id": item.id,
                            "name": item.name,
                            "arguments": item.arguments,
                        }
                        for item in tool_calls
                    ],
                }
            ),
            token_usage=raw.token_usage,
            latency_ms=latency_ms,
            provider_request_id=raw.provider_request_id,
            provider_returned_model=raw.model,
            tool_calls=tool_calls,
        )


class QwenModelExecutionAdapter(OpenAICompatibleModelExecutionAdapter):
    """DashScope specialization retaining Qwen thinking-control arguments."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        timeout_seconds: float,
        max_retries: int = 2,
        client: OpenAI | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            client=client,
            qwen_thinking_control=True,
        )


@dataclass(frozen=True, slots=True)
class _RawCompletion:
    content: str
    finish_reason: str | None
    tool_calls: tuple[dict[str, str], ...]
    token_usage: dict[str, int] | None
    provider_request_id: str | None
    model: str | None


def _consume_completion(
    completion: Any,  # noqa: ANN401
) -> _RawCompletion:
    message = completion.choices[0].message if completion.choices else None
    finish_reason = (
        getattr(completion.choices[0], "finish_reason", None)
        if completion.choices
        else None
    )
    content = getattr(message, "content", None) or ""
    # Provider private reasoning_content is deliberately not read, stored or
    # returned: it must never enter Thread, RunEvent, shares, exports or
    # renderers. Only the governed public path (tool arguments / JSON output)
    # is consumed.
    tool_calls = tuple(
        {
            "id": str(getattr(item, "id", "")),
            "name": str(getattr(getattr(item, "function", None), "name", "")),
            "arguments": str(getattr(getattr(item, "function", None), "arguments", "")),
        }
        for item in (getattr(message, "tool_calls", None) or ())
    )
    returned_model = getattr(completion, "model", None)
    return _RawCompletion(
        content=content,
        finish_reason=finish_reason,
        tool_calls=tool_calls,
        token_usage=_standard_token_usage(getattr(completion, "usage", None)),
        provider_request_id=(
            getattr(completion, "_request_id", None) or getattr(completion, "id", None)
        ),
        model=returned_model
        if isinstance(returned_model, str) and returned_model
        else None,
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


def _elapsed_ms(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))


def _provider_error_code(error: APIStatusError) -> str | None:
    body = getattr(error, "body", None)
    if not isinstance(body, dict):
        return None
    code = body.get("code")
    return code if isinstance(code, str) else None


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
    "OpenAICompatibleModelExecutionAdapter",
    "QwenModelExecutionAdapter",
    "qwen_execution_lease_duration",
]
