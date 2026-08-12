"""Provider-neutral model execution boundary and the pinned Qwen adapter."""

from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import timedelta
from time import monotonic
from typing import Any, Protocol, cast

from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, OpenAI

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
    model: str
    model_revision: str
    prompt_name: str
    prompt_version: str
    prompt_hash: str
    prompt: str
    input_payload: dict[str, Any]
    parameters: dict[str, Any]

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
    token_usage: dict[str, Any] | None
    latency_ms: int
    provider_request_id: str | None


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
        token_usage: dict[str, Any] | None = None,
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

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        if not self._api_key:
            raise ModelRuntimeUnavailable()

        client = cast(OpenAI, self._client)
        started = monotonic()
        try:
            completion = client.chat.completions.create(
                model=request.model_revision,
                messages=[
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
                ],
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
                **request.parameters,
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
        content = completion.choices[0].message.content if completion.choices else None
        provider_request_id = getattr(completion, "_request_id", None) or completion.id
        token_usage = (
            completion.usage.model_dump(exclude_none=True)
            if completion.usage is not None
            else None
        )
        try:
            payload = _parse_json_content(content)
        except (ValueError, IndexError, TypeError) as exc:
            raise ModelExecutionError(
                "MODEL_RESPONSE_INVALID",
                "研究助手返回了无法验证的结果。",
                output_hash=canonical_request_hash({"provider_content": content}),
                token_usage=token_usage,
                latency_ms=latency_ms,
                provider_request_id=provider_request_id,
            ) from exc

        return ModelExecutionResponse(
            payload=payload,
            output_hash=canonical_request_hash(payload),
            token_usage=token_usage,
            latency_ms=latency_ms,
            provider_request_id=provider_request_id,
        )


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
    "ModelRuntimeUnavailable",
    "QwenModelExecutionAdapter",
    "qwen_execution_lease_duration",
]
