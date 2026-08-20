"""Feedback target admission follows each artifact's owning read boundary."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.orm import Session

from app.schemas.paper_summary_api import PaperSummaryRead
from app.services.artifacts import ArtifactReadService
from app.services.feedback_targets import ArtifactVersionTargetReadService


def _unexpected_session() -> Session:
    raise AssertionError("standalone reasoning traces must be rejected before storage read")


class _UnusedPaperSummaryReads:
    async def get_summary(
        self, *, version_id: str, session_id: str
    ) -> PaperSummaryRead:
        raise AssertionError("standalone reasoning traces do not use PaperSummary reads")


def test_whole_version_feedback_rejects_standalone_reasoning_traces() -> None:
    service = ArtifactVersionTargetReadService(
        ArtifactReadService(_unexpected_session),
        paper_summary_reader=_UnusedPaperSummaryReads(),
    )

    with pytest.raises(
        ValueError,
        match="unsupported ArtifactVersion target kind: reasoning_traces",
    ):
        asyncio.run(
            service.validate_version(
                version_id="00000000-0000-0000-0000-000000000001",
                artifact_kind="reasoning_traces",
                session_id="owner-session",
            )
        )
