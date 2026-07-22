"""Feature-flag wiring tests for the persistent workflow store."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.main import create_app
import app.main as main_module
from app.workflow.store import PersistentWorkflowStore
from app.workflow.persistent_executor import PersistentWorkflowExecutor


def test_v1_runtime_keeps_persistent_workflow_disabled_by_default() -> None:
    application = create_app()

    assert application.state.workflow_store is None
    assert application.state.workflow_executor is None


def test_feature_flag_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main_module,
        "settings",
        Settings(_env_file=None, PERSISTENT_WORKFLOW_ENABLED=True),
    )

    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        create_app()


def test_feature_flag_wires_store_without_connecting_eagerly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = Settings(
        _env_file=None,
        PERSISTENT_WORKFLOW_ENABLED=True,
        DATABASE_URL="postgresql+psycopg://user:secret@db.invalid/workflow",
    )
    monkeypatch.setattr(main_module, "settings", configured)

    application = create_app()

    assert isinstance(application.state.workflow_store, PersistentWorkflowStore)
    assert isinstance(application.state.workflow_executor, PersistentWorkflowExecutor)
