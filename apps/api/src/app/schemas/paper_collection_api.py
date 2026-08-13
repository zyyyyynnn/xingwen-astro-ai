"""Transport projections for the PaperCollection read boundary."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .paper_collection import (
    PaperCollection,
    PaperCollectionCandidate,
    PaperDuplicateGroup,
)
from .core import (
    ContentHash,
    EvidenceDetail,
    Identifier,
    ProducerExecutionDetail,
    SourceMode,
    SourceSnapshotDetail,
    UtcDateTime,
)
from .research_input import ResearchInputRef


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)


class PaperCollectionRead(BaseModel):
    """A validated domain payload pinned to one immutable ArtifactVersion."""

    model_config = MODEL_CONFIG

    artifact_version_id: Identifier
    artifact_id: Identifier
    project_id: Identifier
    source_mode: SourceMode
    content_hash: ContentHash
    input_hash: ContentHash
    created_at: UtcDateTime
    collection: PaperCollection
    producer_execution: ProducerExecutionDetail
    source_snapshots: tuple[SourceSnapshotDetail, ...]
    evidence: tuple[EvidenceDetail, ...]


class PaperCollectionCandidateRead(BaseModel):
    """Candidate plus its duplicate, source and Evidence read projections."""

    model_config = MODEL_CONFIG

    candidate: PaperCollectionCandidate
    duplicate_group: PaperDuplicateGroup
    source_snapshot: SourceSnapshotDetail
    evidence: tuple[EvidenceDetail, ...] = Field(min_length=1)


class PaperAccessEvidenceKind(StrEnum):
    publisher_open_access = "publisher_open_access"
    repository_open_access = "repository_open_access"
    author_provided = "author_provided"
    user_provided = "user_provided"


class PaperCandidateMetadataReason(StrEnum):
    access_not_proven = "access_not_proven"
    metadata_url_only = "metadata_url_only"
    paywalled = "paywalled"
    restricted_full_text = "restricted_full_text"
    partial_metadata = "partial_metadata"
    unsupported_access = "unsupported_access"


class PaperCandidateAccessEvidence(BaseModel):
    """Bounded lawful-access assertion retained without restricted content."""

    model_config = MODEL_CONFIG

    kind: PaperAccessEvidenceKind
    license: Annotated[str, Field(min_length=1, max_length=256)]
    evidence_url: Annotated[str, Field(min_length=1, max_length=2048)]


class OpenAccessPaperCandidateInputRequest(BaseModel):
    model_config = MODEL_CONFIG

    mode: Literal["open_access_url"]
    access_url: Annotated[str, Field(min_length=1, max_length=2048)]
    access_evidence: PaperCandidateAccessEvidence
    filename: Annotated[str | None, Field(default=None, min_length=1, max_length=255)]


class ExistingPaperCandidateInputRequest(BaseModel):
    model_config = MODEL_CONFIG

    mode: Literal["existing_research_input"]
    research_input_id: Identifier
    access_evidence: PaperCandidateAccessEvidence


class MetadataOnlyPaperCandidateInputRequest(BaseModel):
    model_config = MODEL_CONFIG

    mode: Literal["metadata_only"]
    reason: PaperCandidateMetadataReason


CreatePaperCandidateInputRequest = Annotated[
    OpenAccessPaperCandidateInputRequest
    | ExistingPaperCandidateInputRequest
    | MetadataOnlyPaperCandidateInputRequest,
    Field(discriminator="mode"),
]


class PaperCandidateInputBinding(BaseModel):
    """Immutable bridge from one selected candidate to a controlled input."""

    model_config = MODEL_CONFIG

    id: Identifier
    project_id: Identifier
    paper_collection_version_id: Identifier
    candidate_id: Identifier
    canonical_paper_id: Identifier
    candidate_source_snapshot_id: Identifier
    candidate_evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    mode: Literal["open_access_url", "existing_research_input", "metadata_only"]
    # ``reused`` identifies an idempotent replay; persisted outcomes remain
    # the two durable business results and never expose a third database state.
    outcome: Literal["accepted", "metadata_only"]
    source_collection_status: Literal["completed", "partial"]
    metadata_reason: PaperCandidateMetadataReason | None = None
    access_evidence: PaperCandidateAccessEvidence | None = None
    access_evidence_hash: ContentHash | None = None
    research_input: ResearchInputRef | None = None
    parse_status: Literal["not_started"] = "not_started"
    created_at: UtcDateTime
    reused: bool = False

    @model_validator(mode="after")
    def validate_outcome(self) -> PaperCandidateInputBinding:
        if self.outcome == "accepted":
            if (
                self.mode == "metadata_only"
                or self.metadata_reason is not None
                or self.access_evidence is None
                or self.access_evidence_hash is None
                or self.research_input is None
            ):
                raise ValueError("accepted binding requires access evidence and input")
        elif (
            self.mode != "metadata_only"
            or self.metadata_reason is None
            or self.access_evidence is not None
            or self.access_evidence_hash is not None
            or self.research_input is not None
        ):
            raise ValueError("metadata_only binding must not claim access or input")
        return self


__all__ = [
    "CreatePaperCandidateInputRequest",
    "ExistingPaperCandidateInputRequest",
    "MetadataOnlyPaperCandidateInputRequest",
    "OpenAccessPaperCandidateInputRequest",
    "PaperAccessEvidenceKind",
    "PaperCandidateAccessEvidence",
    "PaperCandidateInputBinding",
    "PaperCandidateMetadataReason",
    "PaperCollectionCandidateRead",
    "PaperCollectionRead",
]
