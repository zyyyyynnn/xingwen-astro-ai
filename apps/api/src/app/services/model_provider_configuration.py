"""Instance-wide Chat Completions provider configuration and hot runtime swap."""

from __future__ import annotations

from base64 import urlsafe_b64encode
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from urllib.parse import urlsplit, urlunsplit

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    DefaultHttpxClient,
    OpenAI,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ModelProviderConfigurationModel
from app.schemas.core import (
    ConfigureModelProviderRequest,
    ModelProviderConfigurationSource,
    ModelProviderConfigurationStatus,
    ModelProviderPreset,
)
from app.security import SecurityProblem
from app.services.model_execution import (
    ModelExecutionPort,
    ModelExecutionRequest,
    ModelExecutionResponse,
    OpenAICompatibleModelExecutionAdapter,
    QwenModelExecutionAdapter,
)


_CONFIGURATION_ID = "default"
_CONFIGURATION_LOCK_KEY = 730241
_LOCAL_CUSTOM_HOSTS = frozenset(
    {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
)


@dataclass(frozen=True, slots=True)
class StoredModelProviderConfiguration:
    preset: ModelProviderPreset
    base_url: str
    model: str
    encrypted_api_key: str
    api_key_hint: str
    revision: int
    verified_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ModelRuntimeSnapshot:
    port: ModelExecutionPort
    provider: str
    requested_model: str
    explicit_revision: str | None
    revision: int
    source: ModelProviderConfigurationSource | None
    preset: ModelProviderPreset | None
    base_url: str | None
    api_key_hint: str | None
    verified_at: datetime | None
    updated_at: datetime | None


class CredentialCipher:
    """Encrypt provider credentials with a domain-separated application key."""

    def __init__(self, root_secret: str) -> None:
        normalized = root_secret.strip()
        if len(normalized) < 32:
            raise ValueError(
                "model provider configuration key must be at least 32 characters"
            )
        derived = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"xingwen-model-provider-configuration-v1.0.0",
        ).derive(normalized.encode("utf-8"))
        self._fernet = Fernet(urlsafe_b64encode(derived))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError(
                "stored model provider credential cannot be decrypted"
            ) from exc


class ModelProviderConfigurationStore:
    """PostgreSQL authority for the single instance-wide provider override."""

    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory

    def get(self) -> StoredModelProviderConfiguration | None:
        with self._factory() as session:
            row = session.get(ModelProviderConfigurationModel, _CONFIGURATION_ID)
            return _stored(row) if row is not None else None

    def save(
        self,
        *,
        expected_revision: int,
        preset: ModelProviderPreset,
        base_url: str,
        model: str,
        encrypted_api_key: str,
        api_key_hint: str,
        verified_at: datetime,
    ) -> StoredModelProviderConfiguration:
        with self._factory() as session, session.begin():
            session.execute(select(func.pg_advisory_xact_lock(_CONFIGURATION_LOCK_KEY)))
            row = session.get(
                ModelProviderConfigurationModel,
                _CONFIGURATION_ID,
                with_for_update=True,
            )
            _require_configuration_revision(
                expected=expected_revision,
                current=row.revision if row is not None else 0,
            )
            if row is None:
                row = ModelProviderConfigurationModel(
                    id=_CONFIGURATION_ID,
                    preset=preset.value,
                    base_url=base_url,
                    model=model,
                    encrypted_api_key=encrypted_api_key,
                    api_key_hint=api_key_hint,
                    revision=1,
                    verified_at=verified_at,
                    created_at=verified_at,
                    updated_at=verified_at,
                )
                session.add(row)
            else:
                row.preset = preset.value
                row.base_url = base_url
                row.model = model
                row.encrypted_api_key = encrypted_api_key
                row.api_key_hint = api_key_hint
                row.revision += 1
                row.verified_at = verified_at
                row.updated_at = verified_at
            session.flush()
            return _stored(row)

    def delete(self, *, expected_revision: int) -> None:
        with self._factory() as session, session.begin():
            session.execute(select(func.pg_advisory_xact_lock(_CONFIGURATION_LOCK_KEY)))
            row = session.get(
                ModelProviderConfigurationModel,
                _CONFIGURATION_ID,
                with_for_update=True,
            )
            _require_configuration_revision(
                expected=expected_revision,
                current=row.revision if row is not None else 0,
            )
            if row is not None:
                session.delete(row)


class InMemoryModelProviderConfigurationStore:
    """Explicit local/test fallback when no database runtime exists."""

    def __init__(self) -> None:
        self._value: StoredModelProviderConfiguration | None = None
        self._lock = RLock()

    def get(self) -> StoredModelProviderConfiguration | None:
        with self._lock:
            return self._value

    def save(
        self,
        *,
        expected_revision: int,
        preset: ModelProviderPreset,
        base_url: str,
        model: str,
        encrypted_api_key: str,
        api_key_hint: str,
        verified_at: datetime,
    ) -> StoredModelProviderConfiguration:
        with self._lock:
            _require_configuration_revision(
                expected=expected_revision,
                current=self._value.revision if self._value else 0,
            )
            revision = (self._value.revision + 1) if self._value else 1
            self._value = StoredModelProviderConfiguration(
                preset=preset,
                base_url=base_url,
                model=model,
                encrypted_api_key=encrypted_api_key,
                api_key_hint=api_key_hint,
                revision=revision,
                verified_at=verified_at,
                updated_at=verified_at,
            )
            return self._value

    def delete(self, *, expected_revision: int) -> None:
        with self._lock:
            _require_configuration_revision(
                expected=expected_revision,
                current=self._value.revision if self._value else 0,
            )
            self._value = None


ConfigurationStore = (
    ModelProviderConfigurationStore | InMemoryModelProviderConfigurationStore
)


class ModelRuntimeRegistry:
    """Atomically exposes one immutable runtime snapshot to new model calls."""

    def __init__(
        self,
        *,
        fallback: ModelRuntimeSnapshot,
        store: ConfigurationStore,
        cipher: CredentialCipher,
        timeout_seconds: float,
        max_retries: int,
        load_workspace_override: bool = True,
    ) -> None:
        self._fallback = fallback
        self._store = store
        self._cipher = cipher
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._load_workspace_override = load_workspace_override
        self._lock = RLock()
        self._current = fallback
        self.reload()

    def snapshot(self) -> ModelRuntimeSnapshot:
        with self._lock:
            return self._current

    def refresh(self) -> ModelRuntimeSnapshot:
        """Refresh from shared storage while preserving one coherent snapshot."""
        with self._lock:
            stored = self._store.get() if self._load_workspace_override else None
            if stored is None:
                self._current = self._fallback
            elif not self._matches(stored):
                self._current = self._from_stored(stored)
            return self._current

    def reload(self) -> ModelRuntimeSnapshot:
        return self.refresh()

    def _matches(self, stored: StoredModelProviderConfiguration) -> bool:
        return (
            self._current.source is ModelProviderConfigurationSource.workspace
            and self._current.revision == stored.revision
            and self._current.updated_at == stored.updated_at
        )

    def _from_stored(
        self, stored: StoredModelProviderConfiguration
    ) -> ModelRuntimeSnapshot:
        api_key = self._cipher.decrypt(stored.encrypted_api_key)
        adapter_type = (
            QwenModelExecutionAdapter
            if stored.preset is ModelProviderPreset.dashscope
            else OpenAICompatibleModelExecutionAdapter
        )
        return ModelRuntimeSnapshot(
            port=adapter_type(
                api_key=api_key,
                base_url=stored.base_url,
                timeout_seconds=self._timeout_seconds,
                max_retries=self._max_retries,
            ),
            provider=(
                "qwen"
                if stored.preset is ModelProviderPreset.dashscope
                else "openai_compatible"
            ),
            requested_model=stored.model,
            explicit_revision=None,
            revision=stored.revision,
            source=ModelProviderConfigurationSource.workspace,
            preset=stored.preset,
            base_url=stored.base_url,
            api_key_hint=stored.api_key_hint,
            verified_at=stored.verified_at,
            updated_at=stored.updated_at,
        )


class RegistryModelExecutionPort:
    """Delegates each new call to the registry's current immutable snapshot."""

    def __init__(self, registry: ModelRuntimeRegistry) -> None:
        self._registry = registry

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        return self._registry.refresh().port.execute(request)


Probe = Callable[[str, str, str], None]


class ModelProviderConfigurationService:
    def __init__(
        self,
        *,
        store: ConfigurationStore,
        registry: ModelRuntimeRegistry,
        cipher: CredentialCipher,
        writable: bool,
        app_env: str,
        dashscope_base_url: str,
        allowed_custom_hosts: tuple[str, ...],
        timeout_seconds: float,
        max_retries: int,
        probe: Probe | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._cipher = cipher
        self._writable = writable
        self._app_env = app_env.lower()
        self._dashscope_base_url = dashscope_base_url.rstrip("/")
        self._allowed_custom_hosts = frozenset(
            host.strip().lower() for host in allowed_custom_hosts if host.strip()
        )
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._probe = probe or self._probe_chat_completions

    def status(self) -> ModelProviderConfigurationStatus:
        return self._status(self._registry.refresh())

    def configure(
        self, request: ConfigureModelProviderRequest, *, expected_revision: int
    ) -> ModelProviderConfigurationStatus:
        self._require_writable()
        self._require_current_revision(expected_revision)
        api_key = request.api_key.get_secret_value().strip()
        if not api_key:
            raise _configuration_problem(
                422, "MODEL_PROVIDER_API_KEY_REQUIRED", "请输入有效的 API 密钥。"
            )
        base_url = self._base_url(request.preset, request.base_url)
        model = request.model.strip()
        self._probe(api_key, base_url, model)
        now = datetime.now(UTC)
        self._store.save(
            expected_revision=expected_revision,
            preset=request.preset,
            base_url=base_url,
            model=model,
            encrypted_api_key=self._cipher.encrypt(api_key),
            api_key_hint=api_key[-4:],
            verified_at=now,
        )
        return self._status(self._registry.refresh())

    def remove_override(
        self, *, expected_revision: int
    ) -> ModelProviderConfigurationStatus:
        self._require_writable()
        self._require_current_revision(expected_revision)
        if self._store.get() is None:
            raise _configuration_problem(
                409,
                "MODEL_PROVIDER_CONFIGURATION_MANAGED",
                "当前模型服务由部署环境管理，不能在工作台中移除。",
            )
        self._store.delete(expected_revision=expected_revision)
        return self._status(self._registry.refresh())

    def _require_current_revision(self, expected_revision: int) -> None:
        stored = self._store.get()
        _require_configuration_revision(
            expected=expected_revision,
            current=stored.revision if stored else 0,
        )

    def _status(
        self, snapshot: ModelRuntimeSnapshot
    ) -> ModelProviderConfigurationStatus:
        return _status(
            snapshot,
            writable=self._writable,
            dashscope_base_url=self._dashscope_base_url,
        )

    def _require_writable(self) -> None:
        if not self._writable:
            raise _configuration_problem(
                403,
                "MODEL_PROVIDER_CONFIGURATION_READ_ONLY",
                "当前部署由管理员管理模型服务，工作台仅可查看状态。",
            )

    def _base_url(self, preset: ModelProviderPreset, candidate: str | None) -> str:
        if preset is ModelProviderPreset.dashscope:
            return self._dashscope_base_url
        if candidate is None:
            raise _configuration_problem(
                422,
                "MODEL_PROVIDER_BASE_URL_REQUIRED",
                "自定义兼容服务需要填写 API 基础地址。",
            )
        return _normalize_custom_base_url(
            candidate,
            app_env=self._app_env,
            allowed_hosts=self._allowed_custom_hosts,
        )

    def _probe_chat_completions(self, api_key: str, base_url: str, model: str) -> None:
        try:
            with OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=self._timeout_seconds,
                max_retries=self._max_retries,
                http_client=DefaultHttpxClient(follow_redirects=False),
            ) as client:
                completion = client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "user",
                            "content": "Reply with OK to verify this connection.",
                        }
                    ],
                    max_tokens=1,
                )
            if not completion.choices:
                raise _configuration_problem(
                    502,
                    "MODEL_PROVIDER_RESPONSE_INVALID",
                    "服务已响应，但未返回兼容的 Chat Completions 结果。",
                )
        except SecurityProblem:
            raise
        except APITimeoutError as exc:
            raise _configuration_problem(
                502,
                "MODEL_PROVIDER_TIMEOUT",
                "连接测试超时，请检查服务地址或稍后重试。",
            ) from exc
        except APIStatusError as exc:
            if exc.status_code in {401, 403}:
                detail = "服务拒绝了凭据，请检查 API 密钥。"
                code = "MODEL_PROVIDER_AUTH_FAILED"
                status = 422
            elif exc.status_code == 404:
                detail = "未找到兼容接口或模型，请检查基础地址与模型 ID。"
                code = "MODEL_PROVIDER_NOT_FOUND"
                status = 422
            elif exc.status_code == 429:
                detail = "服务当前限流或额度不足，请检查套餐后重试。"
                code = "MODEL_PROVIDER_RATE_LIMITED"
                status = 502
            else:
                detail = "服务未接受连接测试，请检查兼容性配置。"
                code = "MODEL_PROVIDER_REJECTED"
                status = 502
            raise _configuration_problem(status, code, detail) from exc
        except (APIConnectionError, APIError) as exc:
            raise _configuration_problem(
                502,
                "MODEL_PROVIDER_UNREACHABLE",
                "无法连接模型服务，请检查基础地址与网络。",
            ) from exc


def deployment_runtime(
    *,
    api_key: str | None,
    base_url: str,
    model: str,
    explicit_revision: str | None,
    timeout_seconds: float,
    max_retries: int,
) -> ModelRuntimeSnapshot:
    normalized_key = api_key.strip() if api_key else None
    return ModelRuntimeSnapshot(
        port=QwenModelExecutionAdapter(
            api_key=normalized_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        ),
        provider="qwen",
        requested_model=model,
        explicit_revision=explicit_revision,
        revision=0,
        source=(
            ModelProviderConfigurationSource.deployment if normalized_key else None
        ),
        preset=ModelProviderPreset.dashscope if normalized_key else None,
        base_url=base_url if normalized_key else None,
        api_key_hint=normalized_key[-4:] if normalized_key else None,
        verified_at=None,
        updated_at=None,
    )


def _stored(
    row: ModelProviderConfigurationModel,
) -> StoredModelProviderConfiguration:
    return StoredModelProviderConfiguration(
        preset=ModelProviderPreset(row.preset),
        base_url=row.base_url,
        model=row.model,
        encrypted_api_key=row.encrypted_api_key,
        api_key_hint=row.api_key_hint,
        revision=row.revision,
        verified_at=_utc(row.verified_at),
        updated_at=_utc(row.updated_at),
    )


def _status(
    snapshot: ModelRuntimeSnapshot,
    *,
    writable: bool,
    dashscope_base_url: str,
) -> ModelProviderConfigurationStatus:
    configured = snapshot.source is not None
    return ModelProviderConfigurationStatus(
        status="ready" if configured else "unconfigured",
        revision=snapshot.revision,
        source=snapshot.source,
        preset=snapshot.preset,
        base_url=snapshot.base_url,
        dashscope_base_url=dashscope_base_url,
        model=snapshot.requested_model if configured else None,
        api_key_hint=(
            f"••••{snapshot.api_key_hint}" if snapshot.api_key_hint else None
        ),
        verified_at=snapshot.verified_at,
        updated_at=snapshot.updated_at,
        editable=writable
        and snapshot.source is not ModelProviderConfigurationSource.deployment,
    )


def _normalize_custom_base_url(
    value: str, *, app_env: str, allowed_hosts: frozenset[str]
) -> str:
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or "").lower()
    local_allowed = app_env in {"development", "test", "integration"}
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise _configuration_problem(
            422,
            "MODEL_PROVIDER_BASE_URL_INVALID",
            "API 基础地址必须是无凭据、查询参数和片段的 HTTP(S) 地址。",
        )
    if parsed.scheme != "https" and not (local_allowed and host in _LOCAL_CUSTOM_HOSTS):
        raise _configuration_problem(
            422,
            "MODEL_PROVIDER_HTTPS_REQUIRED",
            "远程模型服务必须使用 HTTPS；本地开发服务可使用 HTTP。",
        )
    allowed = host in allowed_hosts or (local_allowed and host in _LOCAL_CUSTOM_HOSTS)
    if not allowed:
        raise _configuration_problem(
            422,
            "MODEL_PROVIDER_HOST_NOT_ALLOWED",
            "该服务地址未列入部署允许的模型服务主机。",
        )
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _configuration_problem(status: int, code: str, detail: str) -> SecurityProblem:
    return SecurityProblem(
        status=status,
        code=code,
        title="Model provider configuration failed",
        detail=detail,
    )


def _require_configuration_revision(*, expected: int, current: int) -> None:
    if expected != current:
        raise _configuration_problem(
            409,
            "MODEL_PROVIDER_CONFIGURATION_CONFLICT",
            "模型服务配置已更新，请刷新状态后重试。",
        )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = [
    "CredentialCipher",
    "InMemoryModelProviderConfigurationStore",
    "ModelProviderConfigurationService",
    "ModelProviderConfigurationStore",
    "ModelRuntimeRegistry",
    "ModelRuntimeSnapshot",
    "RegistryModelExecutionPort",
    "deployment_runtime",
]
