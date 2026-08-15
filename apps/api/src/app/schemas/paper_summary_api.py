"""Transport projections for the paper-summary read boundary."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from .enums import UpstreamFailureClass
from .paper_summary import PaperSummaryArtifactContent, PaperSummaryPaperMetadata
from .core import (
    ContentHash,
    EvidenceDetail,
    Identifier,
    ProducerExecutionDetail,
    SourceMode,
    SourceSnapshotDetail,
    UtcDateTime,
)


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)


def _reject_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("value must not be blank")
    return value


NonBlankString = Annotated[
    str,
    Field(min_length=1),
    AfterValidator(_reject_blank),
]


class PaperSummaryCacheAudit(BaseModel):
    """Why a cached source was used and the immutable origin it came from."""

    model_config = MODEL_CONFIG

    source_id: Identifier
    source_snapshot_id: Identifier
    cache_version: NonBlankString
    cache_applicability: NonBlankString
    live_failure_class: UpstreamFailureClass
    live_failure_code: NonBlankString
    origin_run_id: Identifier
    origin_artifact_version_id: Identifier


class PaperSummaryRead(BaseModel):
    """A validated PaperSummary pinned to one immutable ArtifactVersion."""

    model_config = MODEL_CONFIG

    artifact_version_id: Identifier
    artifact_id: Identifier
    project_id: Identifier
    version_number: int = Field(ge=1)
    supersedes_version_id: Identifier | None
    source_mode: SourceMode
    content_hash: ContentHash
    input_hash: ContentHash
    created_at: UtcDateTime
    paper: PaperSummaryPaperMetadata
    summary: PaperSummaryArtifactContent
    cache_audits: tuple[PaperSummaryCacheAudit, ...] = ()
    producer_execution: ProducerExecutionDetail
    source_snapshots: tuple[SourceSnapshotDetail, ...]
    evidence: tuple[EvidenceDetail, ...]


__all__ = [
    "PaperSummaryCacheAudit",
    "PaperSummaryPaperMetadata",
    "PaperSummaryRead",
]
