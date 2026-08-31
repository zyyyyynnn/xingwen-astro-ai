"""The operator command uses the same typed planning path as the API."""

import json
from pathlib import Path
from types import SimpleNamespace

from pydantic import SecretStr
from app.test_support.integration_model import (
    DeterministicIntegrationModelExecutionPort,
)
from scripts import qualify_research_assistant as command


def test_qualification_emits_actual_execution_identity(monkeypatch, capsys) -> None:
    monkeypatch.chdir(Path(__file__).resolve().parents[3])
    monkeypatch.setattr(
        command,
        "settings",
        SimpleNamespace(
            research_assistant_ready=True,
            DASHSCOPE_API_KEY=SecretStr("test-key-never-persisted"),
            DASHSCOPE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1",
            DASHSCOPE_TIMEOUT_SECONDS=30,
            DASHSCOPE_MODEL="operator-selected-model",
            DASHSCOPE_EXPLICIT_MODEL_REVISION=None,
        ),
    )
    monkeypatch.setattr(command.sys, "argv", ["qualify_research_assistant.py"])
    monkeypatch.setattr(
        command,
        "QwenModelExecutionAdapter",
        lambda **_kwargs: DeterministicIntegrationModelExecutionPort(),
    )

    assert command.main() == 0
    output = capsys.readouterr().out
    evidence = json.loads(output)
    assert evidence["provider"] == "dashscope"
    assert evidence["requested_model"] == "operator-selected-model"
    assert evidence["provider_returned_model"] == "deterministic-integration-planner"
    assert evidence["explicit_revision"] is None
    assert evidence["provider_request_id"] == "integration-deterministic-planner"
    assert "test-key-never-persisted" not in output


def test_unconfigured_qualification_does_not_call_provider(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        command,
        "settings",
        SimpleNamespace(
            research_assistant_ready=False,
            DASHSCOPE_API_KEY=None,
        ),
    )
    assert command.main() == 2
    assert json.loads(capsys.readouterr().out)["code"] == "MODEL_RUNTIME_UNAVAILABLE"
