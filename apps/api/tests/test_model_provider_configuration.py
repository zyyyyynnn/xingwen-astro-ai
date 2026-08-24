from __future__ import annotations

from dataclasses import replace
import os
from types import SimpleNamespace

import pytest
from sqlalchemy import Engine

from db_bootstrap import reset_current_schema
from app.db.session import create_engine_from_url, session_factory

from app.schemas.core import (
    ConfigureModelProviderRequest,
    ModelProviderConfigurationSource,
    ModelProviderPreset,
)
from app.security import SecurityProblem
from app.services.model_execution import ModelRuntimeUnavailable
import app.services.model_provider_configuration as configuration_module
from app.services.model_provider_configuration import (
    CredentialCipher,
    InMemoryModelProviderConfigurationStore,
    ModelProviderConfigurationService,
    ModelProviderConfigurationStore,
    ModelRuntimeRegistry,
    ModelRuntimeSnapshot,
    RegistryModelExecutionPort,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


class UnconfiguredPort:
    def execute(self, _request):  # noqa: ANN001, ANN201
        raise ModelRuntimeUnavailable()


def fallback_runtime(*, configured: bool = False) -> ModelRuntimeSnapshot:
    return ModelRuntimeSnapshot(
        port=UnconfiguredPort(),
        provider="qwen",
        requested_model="qwen3.8-max",
        explicit_revision=None,
        revision=0,
        source=(ModelProviderConfigurationSource.deployment if configured else None),
        preset=(ModelProviderPreset.dashscope if configured else None),
        base_url=(
            "https://dashscope.aliyuncs.com/compatible-mode/v1" if configured else None
        ),
        api_key_hint="1234" if configured else None,
        verified_at=None,
        updated_at=None,
    )


def service(
    *,
    writable: bool = True,
    configured_fallback: bool = False,
    allowed_hosts: tuple[str, ...] = (),
    probe=None,  # noqa: ANN001
):
    store = InMemoryModelProviderConfigurationStore()
    cipher = CredentialCipher("test-model-provider-root-secret-0001")
    registry = ModelRuntimeRegistry(
        fallback=fallback_runtime(configured=configured_fallback),
        store=store,
        cipher=cipher,
        timeout_seconds=3,
        max_retries=0,
    )
    tested: list[tuple[str, str, str]] = []

    def successful_probe(api_key: str, base_url: str, model: str) -> None:
        tested.append((api_key, base_url, model))

    return (
        ModelProviderConfigurationService(
            store=store,
            registry=registry,
            cipher=cipher,
            writable=writable,
            app_env="development",
            dashscope_base_url=("https://dashscope.aliyuncs.com/compatible-mode/v1"),
            allowed_custom_hosts=allowed_hosts,
            timeout_seconds=3,
            max_retries=0,
            probe=probe or successful_probe,
        ),
        store,
        registry,
        tested,
    )


def request(**overrides):  # noqa: ANN003, ANN201
    return ConfigureModelProviderRequest.model_validate(
        {
            "preset": "dashscope",
            "base_url": None,
            "model": "qwen3.8-max",
            "api_key": "secret-key-1234",
            **overrides,
        }
    )


def test_configuration_is_verified_encrypted_and_installed_globally() -> None:
    configuration, store, registry, tested = service()

    status = configuration.configure(request(), expected_revision=0)

    stored = store.get()
    assert status.status == "ready"
    assert status.revision == 1
    assert status.source == "workspace"
    assert status.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert status.dashscope_base_url == status.base_url
    assert status.api_key_hint == "••••1234"
    assert status.editable is True
    assert tested == [
        (
            "secret-key-1234",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "qwen3.8-max",
        )
    ]
    assert stored is not None
    assert "secret-key-1234" not in stored.encrypted_api_key
    assert registry.snapshot().requested_model == "qwen3.8-max"
    assert registry.snapshot().provider == "qwen"


def test_model_id_is_not_limited_to_repository_test_baselines() -> None:
    configuration, _store, registry, tested = service()

    status = configuration.configure(request(model="qwen-plus"), expected_revision=0)

    assert status.model == "qwen-plus"
    assert tested[-1][2] == "qwen-plus"
    assert registry.snapshot().requested_model == "qwen-plus"


def test_stale_configuration_revision_fails_before_connection_probe() -> None:
    configuration, store, registry, tested = service()
    configuration.configure(request(), expected_revision=0)

    with pytest.raises(SecurityProblem) as captured:
        configuration.configure(
            request(model="qwen-plus"),
            expected_revision=0,
        )

    assert captured.value.status == 409
    assert captured.value.code == "MODEL_PROVIDER_CONFIGURATION_CONFLICT"
    assert len(tested) == 1
    assert store.get() is not None
    assert registry.snapshot().requested_model == "qwen3.8-max"


def test_status_uses_configuration_and_revision_from_one_store_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuration, store, _registry, _tested = service()
    configuration.configure(request(), expected_revision=0)
    stored = store.get()
    assert stored is not None
    newer = replace(stored, model="qwen-plus", revision=2)
    reads = iter((stored, newer))
    monkeypatch.setattr(store, "get", lambda: next(reads))

    status = configuration.status()

    assert status.model == "qwen3.8-max"
    assert status.revision == 1


def test_new_model_call_refreshes_an_override_written_by_another_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RefreshedPort:
        def __init__(self, **_kwargs):  # noqa: ANN003
            pass

        def execute(self, _request):  # noqa: ANN001, ANN201
            return "refreshed-runtime"

    monkeypatch.setattr(
        configuration_module, "QwenModelExecutionAdapter", RefreshedPort
    )
    store = InMemoryModelProviderConfigurationStore()
    cipher = CredentialCipher("test-model-provider-root-secret-0001")
    first_registry = ModelRuntimeRegistry(
        fallback=fallback_runtime(),
        store=store,
        cipher=cipher,
        timeout_seconds=3,
        max_retries=0,
    )
    second_registry = ModelRuntimeRegistry(
        fallback=fallback_runtime(),
        store=store,
        cipher=cipher,
        timeout_seconds=3,
        max_retries=0,
    )
    configuration = ModelProviderConfigurationService(
        store=store,
        registry=first_registry,
        cipher=cipher,
        writable=True,
        app_env="development",
        dashscope_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        allowed_custom_hosts=(),
        timeout_seconds=3,
        max_retries=0,
        probe=lambda _api_key, _base_url, _model: None,
    )
    configuration.configure(request(model="qwen-plus"), expected_revision=0)
    assert second_registry.snapshot().source is None

    result = RegistryModelExecutionPort(second_registry).execute(object())

    assert result == "refreshed-runtime"
    assert second_registry.snapshot().requested_model == "qwen-plus"
    assert second_registry.snapshot().revision == 1


def test_probe_transport_never_follows_provider_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport_options: dict[str, object] = {}
    client_options: dict[str, object] = {}
    transport = SimpleNamespace(follow_redirects=False)

    def build_transport(**kwargs):  # noqa: ANN003, ANN201
        transport_options.update(kwargs)
        return transport

    class ProbeClient:
        chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **_kwargs: SimpleNamespace(choices=[object()])
            )
        )

        def __init__(self, **kwargs):  # noqa: ANN003
            client_options.update(kwargs)

        def __enter__(self):  # noqa: ANN201
            return self

        def __exit__(self, *_args):  # noqa: ANN002, ANN201
            return False

    monkeypatch.setattr(configuration_module, "DefaultHttpxClient", build_transport)
    monkeypatch.setattr(configuration_module, "OpenAI", ProbeClient)
    configuration, _store, _registry, _tested = service()

    configuration._probe_chat_completions(
        "secret-key-1234",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen-plus",
    )

    assert transport_options == {"follow_redirects": False}
    assert client_options["http_client"] is transport


def test_custom_provider_requires_an_allowed_host_but_accepts_local_docker() -> None:
    configuration, _store, registry, tested = service()

    status = configuration.configure(
        request(
            preset="custom",
            base_url="http://host.docker.internal:11434/v1/",
        ),
        expected_revision=0,
    )
    assert status.base_url == "http://host.docker.internal:11434/v1"
    assert tested[0][1] == "http://host.docker.internal:11434/v1"
    assert registry.snapshot().provider == "openai_compatible"

    with pytest.raises(SecurityProblem) as captured:
        configuration.configure(
            request(preset="custom", base_url="https://metadata.internal/v1"),
            expected_revision=1,
        )
    assert captured.value.status == 422
    assert captured.value.code == "MODEL_PROVIDER_HOST_NOT_ALLOWED"


def test_failed_probe_does_not_replace_the_active_configuration() -> None:
    def rejected(_api_key: str, _base_url: str, _model: str) -> None:
        raise SecurityProblem(
            status=422,
            code="MODEL_PROVIDER_AUTH_FAILED",
            title="rejected",
            detail="服务拒绝了凭据，请检查 API 密钥。",
        )

    configuration, store, registry, _tested = service(probe=rejected)

    with pytest.raises(SecurityProblem):
        configuration.configure(request(), expected_revision=0)

    assert store.get() is None
    assert registry.snapshot().source is None


def test_deployment_configuration_is_visible_but_not_mutable() -> None:
    configuration, _store, _registry, _tested = service(
        writable=False, configured_fallback=True
    )

    status = configuration.status()
    assert status.status == "ready"
    assert status.source == "deployment"
    assert status.editable is False

    with pytest.raises(SecurityProblem) as captured:
        configuration.configure(request(), expected_revision=0)
    assert captured.value.status == 403


def test_production_registry_ignores_a_stale_workspace_override() -> None:
    configuration, store, _registry, _tested = service()
    configuration.configure(request(), expected_revision=0)
    cipher = CredentialCipher("test-model-provider-root-secret-0001")

    registry = ModelRuntimeRegistry(
        fallback=fallback_runtime(configured=True),
        store=store,
        cipher=cipher,
        timeout_seconds=3,
        max_retries=0,
        load_workspace_override=False,
    )

    assert registry.snapshot().source == ModelProviderConfigurationSource.deployment
    assert registry.snapshot().requested_model == "qwen3.8-max"


def test_removing_workspace_override_returns_to_deployment_baseline() -> None:
    configuration, _store, _registry, _tested = service(configured_fallback=True)
    configuration.configure(request(), expected_revision=0)

    status = configuration.remove_override(expected_revision=1)

    assert status.source == "deployment"
    assert status.revision == 0
    assert status.model == "qwen3.8-max"
    assert status.editable is False


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured")
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
    )
    reset_current_schema(TEST_DATABASE_URL)
    engine = create_engine_from_url(TEST_DATABASE_URL)
    yield engine
    engine.dispose()
    reset_current_schema(TEST_DATABASE_URL)


def test_postgres_configuration_survives_registry_restart(
    postgres_engine: Engine,
) -> None:
    store = ModelProviderConfigurationStore(session_factory(postgres_engine))
    cipher = CredentialCipher("postgres-model-provider-root-secret-0001")
    first_registry = ModelRuntimeRegistry(
        fallback=fallback_runtime(),
        store=store,
        cipher=cipher,
        timeout_seconds=3,
        max_retries=0,
    )
    configuration = ModelProviderConfigurationService(
        store=store,
        registry=first_registry,
        cipher=cipher,
        writable=True,
        app_env="test",
        dashscope_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        allowed_custom_hosts=(),
        timeout_seconds=3,
        max_retries=0,
        probe=lambda _api_key, _base_url, _model: None,
    )

    configuration.configure(request(), expected_revision=0)
    stored = store.get()
    assert stored is not None
    assert "secret-key-1234" not in stored.encrypted_api_key

    restarted_registry = ModelRuntimeRegistry(
        fallback=fallback_runtime(),
        store=ModelProviderConfigurationStore(session_factory(postgres_engine)),
        cipher=CredentialCipher("postgres-model-provider-root-secret-0001"),
        timeout_seconds=3,
        max_retries=0,
    )
    restarted = restarted_registry.snapshot()
    assert restarted.source == ModelProviderConfigurationSource.workspace
    assert restarted.requested_model == "qwen3.8-max"
    assert restarted.api_key_hint == "1234"
