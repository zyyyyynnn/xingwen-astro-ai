"""Composition root for the sole current versionless ``/api`` contract."""

from __future__ import annotations

from fastapi import FastAPI

from app.contracts.core import PROBLEM_RESPONSES, create_contract_app
from app.contracts.data_artifacts import register_data_artifact_contract


def create_current_contract_app() -> FastAPI:
    """Build the generated transport contract from current domain families."""

    app = create_contract_app()
    register_data_artifact_contract(app, problem_responses=PROBLEM_RESPONSES)
    return app
