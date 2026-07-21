"""Pydantic authoring source for the minimal ``/api/v2`` core contract."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


V2_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ResearchGoal = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=4, max_length=500),
]
SemanticVersion = Annotated[str, Field(pattern=r"^[1-9]\d*\.\d+\.\d+$")]
ContentHash = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
DataCell = str | int | float | bool | None


def _require_utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("datetime must use UTC")
    return value


UtcDateTime = Annotated[AwareDatetime, AfterValidator(_require_utc)]


class ExecutionMode(StrEnum):
    demo_replay = "demo_replay"
    live = "live"


class SourceMode(StrEnum):
    fixture = "fixture"
    live = "live"
    cached = "cached"


class DerivationKind(StrEnum):
    original = "original"
    retry = "retry"
    revision = "revision"
    fork = "fork"


class RunStatus(StrEnum):
    queued = "queued"
    planning = "planning"
    fetching_data = "fetching_data"
    cleaning_data = "cleaning_data"
    searching_papers = "searching_papers"
    summarizing_papers = "summarizing_papers"
    reasoning_literature = "reasoning_literature"
    building_graph = "building_graph"
    waiting_for_input = "waiting_for_input"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ArtifactKind(StrEnum):
    dataset = "dataset"
    field_dictionary = "field_dictionary"
    source_collection = "source_collection"
    paper_collection = "paper_collection"
    paper_summary = "paper_summary"
    literature_claims = "literature_claims"
    literature_relations = "literature_relations"
    reasoning_traces = "reasoning_traces"
    graph = "graph"
    export = "export"


class ContractDraftStatus(StrEnum):
    draft = "draft"
    confirmed = "confirmed"
    expired = "expired"


class UnitPolicy(StrEnum):
    canonical = "canonical"


class CachePolicy(StrEnum):
    disabled = "disabled"
    fallback_on_recoverable_failure = "fallback_on_recoverable_failure"


class DataRequirements(BaseModel):
    model_config = V2_MODEL_CONFIG

    unit_policy: UnitPolicy = UnitPolicy.canonical


class SourceScope(BaseModel):
    model_config = V2_MODEL_CONFIG

    allowed_sources: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_sources(self) -> SourceScope:
        if len(self.allowed_sources) != len(set(self.allowed_sources)):
            raise ValueError("allowed_sources must not contain duplicates")
        return self


class PaperSearchScope(BaseModel):
    model_config = V2_MODEL_CONFIG

    keywords: tuple[NonEmptyString, ...] = ()
    year_from: int | None = Field(default=None, ge=1900, le=9999)
    year_to: int | None = Field(default=None, ge=1900, le=9999)
    source_ids: tuple[Identifier, ...] = ()
    max_candidates: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_year_range(self) -> PaperSearchScope:
        if self.year_from is not None and self.year_to is not None:
            if self.year_from > self.year_to:
                raise ValueError("year_from must not exceed year_to")
        return self


class EvidenceRequirements(BaseModel):
    model_config = V2_MODEL_CONFIG

    require_locator: bool = True
    require_source_snapshot: bool = True
    minimum_coverage: float = Field(default=1.0, ge=0, le=1)


class QualityConstraints(BaseModel):
    model_config = V2_MODEL_CONFIG

    source_completeness_min: float = Field(default=1.0, ge=0, le=1)
    unit_consistency_min: float = Field(default=1.0, ge=0, le=1)


class ResearchContractInput(BaseModel):
    """Shared scientific payload for an editable draft and immutable contract."""

    model_config = V2_MODEL_CONFIG

    research_goal: ResearchGoal
    target_objects: tuple[Identifier, ...] = Field(min_length=1)
    data_requirements: DataRequirements
    requested_fields: tuple[Identifier, ...] = Field(min_length=1)
    source_scope: SourceScope
    paper_search_scope: PaperSearchScope
    output_requirements: tuple[ArtifactKind, ...] = Field(min_length=1)
    evidence_requirements: EvidenceRequirements
    quality_constraints: QualityConstraints

    @model_validator(mode="after")
    def require_unique_contract_values(self) -> ResearchContractInput:
        for field_name in ("target_objects", "requested_fields", "output_requirements"):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class ResearchProject(BaseModel):
    model_config = ConfigDict(
        **V2_MODEL_CONFIG,
        json_schema_extra={
            "examples": [
                {
                    "id": "proj_01JEXAMPLE",
                    "session_id": "sess_01JEXAMPLE",
                    "name": "Exoplanet host-star integration",
                    "description": "Evidence-bound integration for the frozen main case",
                    "case_key": "exoplanet_host_star",
                    "created_at": "2026-07-21T08:00:00Z",
                    "updated_at": "2026-07-21T08:00:00Z",
                    "revision": 1,
                }
            ]
        },
    )

    id: Identifier
    session_id: Identifier
    name: NonEmptyString
    description: str = ""
    case_key: Literal["exoplanet_host_star"]
    active_contract_id: Identifier | None = None
    latest_run_id: Identifier | None = None
    created_at: UtcDateTime
    updated_at: UtcDateTime
    revision: int = Field(ge=1)


class ResearchContractDraft(BaseModel):
    model_config = ConfigDict(
        **V2_MODEL_CONFIG,
        json_schema_extra={
            "examples": [
                {
                    "id": "rcd_01JEXAMPLE",
                    "session_id": "sess_01JEXAMPLE",
                    "version": 1,
                    "intent": "Integrate exoplanet candidates and host-star parameters",
                    "status": "draft",
                    "contract": {
                        "research_goal": "Integrate exoplanet candidates and host-star parameters",
                        "target_objects": ["exoplanet_candidate", "host_star"],
                        "data_requirements": {"unit_policy": "canonical"},
                        "requested_fields": ["planet.toi_id", "star.tic_id"],
                        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
                        "paper_search_scope": {"max_candidates": 20},
                        "output_requirements": ["dataset", "graph"],
                        "evidence_requirements": {},
                        "quality_constraints": {},
                    },
                    "warnings": [],
                    "created_at": "2026-07-21T08:00:00Z",
                    "updated_at": "2026-07-21T08:00:00Z",
                    "expires_at": "2026-07-21T09:00:00Z",
                }
            ]
        },
    )

    id: Identifier
    session_id: Identifier
    version: int = Field(ge=1)
    intent: NonEmptyString
    status: ContractDraftStatus = ContractDraftStatus.draft
    contract: ResearchContractInput
    warnings: tuple[str, ...] = ()
    created_at: UtcDateTime
    updated_at: UtcDateTime
    expires_at: UtcDateTime


class ResearchContract(ResearchContractInput):
    model_config = ConfigDict(
        **V2_MODEL_CONFIG,
        json_schema_extra={
            "examples": [
                {
                    "id": "rc_01JEXAMPLE",
                    "project_id": "proj_01JEXAMPLE",
                    "version": 1,
                    "research_goal": "Integrate exoplanet candidates and host-star parameters",
                    "target_objects": ["exoplanet_candidate", "host_star"],
                    "data_requirements": {"unit_policy": "canonical"},
                    "requested_fields": ["planet.toi_id", "star.tic_id"],
                    "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
                    "paper_search_scope": {"max_candidates": 20},
                    "output_requirements": ["dataset", "graph"],
                    "evidence_requirements": {},
                    "quality_constraints": {},
                    "created_from_draft_id": "rcd_01JEXAMPLE",
                    "created_at": "2026-07-21T08:00:00Z",
                    "content_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                }
            ]
        },
    )

    id: Identifier
    project_id: Identifier
    version: int = Field(ge=1)
    created_from_draft_id: Identifier
    created_at: UtcDateTime
    content_hash: ContentHash


class ResearchRun(BaseModel):
    model_config = ConfigDict(
        **V2_MODEL_CONFIG,
        json_schema_extra={
            "examples": [
                {
                    "id": "run_01JEXAMPLE",
                    "project_id": "proj_01JEXAMPLE",
                    "contract_id": "rc_01JEXAMPLE",
                    "execution_mode": "live",
                    "status": "queued",
                    "progress": 0,
                    "parent_run_id": None,
                    "derivation_kind": "original",
                    "retry_from_step": None,
                    "cache_policy": "fallback_on_recoverable_failure",
                    "created_at": "2026-07-21T08:00:00Z",
                    "updated_at": "2026-07-21T08:00:00Z",
                    "latest_event_sequence": 0,
                }
            ]
        },
    )

    id: Identifier
    project_id: Identifier
    contract_id: Identifier
    execution_mode: ExecutionMode
    status: RunStatus
    progress: int = Field(ge=0, le=100)
    parent_run_id: Identifier | None = None
    derivation_kind: DerivationKind
    retry_from_step: Identifier | None = None
    cache_policy: CachePolicy
    started_at: UtcDateTime | None = None
    finished_at: UtcDateTime | None = None
    created_at: UtcDateTime
    updated_at: UtcDateTime
    latest_event_sequence: int = Field(default=0, ge=0)
    failure_code: str | None = None
    failure_summary: str | None = None

    @model_validator(mode="after")
    def validate_derivation(self) -> ResearchRun:
        if self.derivation_kind is DerivationKind.original and self.parent_run_id is not None:
            raise ValueError("original run must not have parent_run_id")
        if self.derivation_kind is not DerivationKind.original and self.parent_run_id is None:
            raise ValueError("derived run must have parent_run_id")
        if self.retry_from_step is not None and self.derivation_kind is not DerivationKind.retry:
            raise ValueError("retry_from_step is only valid for retry runs")
        if self.status is RunStatus.completed and self.progress != 100:
            raise ValueError("completed run must have progress 100")
        return self


class RunEvent(BaseModel):
    model_config = ConfigDict(
        **V2_MODEL_CONFIG,
        json_schema_extra={
            "examples": [
                {
                    "run_id": "run_01JEXAMPLE",
                    "sequence": 1,
                    "event_type": "run.queued",
                    "step_key": None,
                    "progress": 0,
                    "public_message": "Run queued",
                    "artifact_version_ids": [],
                    "occurred_at": "2026-07-21T08:00:00Z",
                }
            ]
        },
    )

    run_id: Identifier
    sequence: int = Field(ge=1)
    event_type: Identifier
    step_key: Identifier | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    public_message: str
    artifact_version_ids: tuple[Identifier, ...] = ()
    occurred_at: UtcDateTime


class ResearchArtifact(BaseModel):
    model_config = ConfigDict(
        **V2_MODEL_CONFIG,
        json_schema_extra={
            "examples": [
                {
                    "id": "art_01JEXAMPLE",
                    "project_id": "proj_01JEXAMPLE",
                    "kind": "dataset",
                    "title": "Exoplanet host-star dataset",
                    "logical_key": "dataset.primary",
                    "created_at": "2026-07-21T08:00:00Z",
                    "latest_version_id": "artv_01JEXAMPLE",
                }
            ]
        },
    )

    id: Identifier
    project_id: Identifier
    kind: ArtifactKind
    title: NonEmptyString
    logical_key: Identifier
    created_at: UtcDateTime
    latest_version_id: Identifier | None = None


class ProducerReference(BaseModel):
    model_config = V2_MODEL_CONFIG

    type: Literal["pipeline", "model", "algorithm"]
    name: NonEmptyString
    version: NonEmptyString
    model_name: str | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None
    parameters_hash: ContentHash | None = None


class DatasetArtifactContent(BaseModel):
    model_config = V2_MODEL_CONFIG

    kind: Literal[ArtifactKind.dataset]
    field_ids: tuple[Identifier, ...] = Field(min_length=1)
    rows: tuple[dict[Identifier, DataCell], ...]

    @model_validator(mode="after")
    def validate_fields(self) -> DatasetArtifactContent:
        if len(self.field_ids) != len(set(self.field_ids)):
            raise ValueError("field_ids must not contain duplicates")
        declared = set(self.field_ids)
        unknown = sorted({key for row in self.rows for key in row} - declared)
        if unknown:
            raise ValueError(f"dataset rows contain undeclared field(s): {unknown}")
        return self


class FieldDictionaryArtifactContent(BaseModel):
    model_config = V2_MODEL_CONFIG

    kind: Literal[ArtifactKind.field_dictionary]
    field_ids: tuple[Identifier, ...] = Field(min_length=1)


class SourceCollectionArtifactContent(BaseModel):
    model_config = V2_MODEL_CONFIG

    kind: Literal[ArtifactKind.source_collection]
    source_snapshot_ids: tuple[Identifier, ...] = Field(min_length=1)


class PaperCollectionArtifactContent(BaseModel):
    model_config = V2_MODEL_CONFIG

    kind: Literal[ArtifactKind.paper_collection]
    paper_ids: tuple[Identifier, ...]


class PaperSummaryArtifactContent(BaseModel):
    model_config = V2_MODEL_CONFIG

    kind: Literal[ArtifactKind.paper_summary]
    paper_id: Identifier
    summary_id: Identifier


class LiteratureClaimsArtifactContent(BaseModel):
    model_config = V2_MODEL_CONFIG

    kind: Literal[ArtifactKind.literature_claims]
    claim_ids: tuple[Identifier, ...]


class LiteratureRelationsArtifactContent(BaseModel):
    model_config = V2_MODEL_CONFIG

    kind: Literal[ArtifactKind.literature_relations]
    relation_ids: tuple[Identifier, ...]


class ReasoningTracesArtifactContent(BaseModel):
    model_config = V2_MODEL_CONFIG

    kind: Literal[ArtifactKind.reasoning_traces]
    reasoning_trace_ids: tuple[Identifier, ...]


class GraphArtifactContent(BaseModel):
    model_config = V2_MODEL_CONFIG

    kind: Literal[ArtifactKind.graph]
    node_ids: tuple[Identifier, ...]
    edge_ids: tuple[Identifier, ...]


class ExportArtifactContent(BaseModel):
    model_config = V2_MODEL_CONFIG

    kind: Literal[ArtifactKind.export]
    format: Literal["csv", "json", "provenance_report"]
    artifact_version_ids: tuple[Identifier, ...] = Field(min_length=1)


ArtifactContent = Annotated[
    DatasetArtifactContent
    | FieldDictionaryArtifactContent
    | SourceCollectionArtifactContent
    | PaperCollectionArtifactContent
    | PaperSummaryArtifactContent
    | LiteratureClaimsArtifactContent
    | LiteratureRelationsArtifactContent
    | ReasoningTracesArtifactContent
    | GraphArtifactContent
    | ExportArtifactContent,
    Field(discriminator="kind"),
]


class ArtifactVersion(BaseModel):
    model_config = ConfigDict(
        **V2_MODEL_CONFIG,
        json_schema_extra={
            "examples": [
                {
                    "id": "artv_01JEXAMPLE",
                    "artifact_id": "art_01JEXAMPLE",
                    "project_id": "proj_01JEXAMPLE",
                    "created_by_run_id": "run_01JEXAMPLE",
                    "version_number": 1,
                    "schema_version": "2.0.0",
                    "content": {
                        "kind": "dataset",
                        "field_ids": ["planet.toi_id"],
                        "rows": [],
                    },
                    "content_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "input_hash": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    "source_mode": "live",
                    "producer": {"type": "pipeline", "name": "data", "version": "1.0.0"},
                    "source_snapshot_ids": [],
                    "evidence_ids": [],
                    "supersedes_version_id": None,
                    "created_at": "2026-07-21T08:00:00Z",
                }
            ]
        },
    )

    id: Identifier
    artifact_id: Identifier
    project_id: Identifier
    created_by_run_id: Identifier
    version_number: int = Field(ge=1)
    schema_version: SemanticVersion
    content: ArtifactContent
    content_hash: ContentHash
    input_hash: ContentHash
    source_mode: SourceMode
    producer: ProducerReference
    source_snapshot_ids: tuple[Identifier, ...] = ()
    evidence_ids: tuple[Identifier, ...] = ()
    supersedes_version_id: Identifier | None = None
    created_at: UtcDateTime


class ResponseMeta(BaseModel):
    model_config = V2_MODEL_CONFIG

    request_id: Identifier
    schema_version: Literal["2.0.0"] = "2.0.0"
    generated_at: UtcDateTime


class ResponseLinks(BaseModel):
    model_config = V2_MODEL_CONFIG

    self: NonEmptyString


DataT = TypeVar("DataT")


class Envelope(BaseModel, Generic[DataT]):
    model_config = V2_MODEL_CONFIG

    data: DataT
    meta: ResponseMeta
    links: ResponseLinks


class CursorPage(BaseModel):
    model_config = V2_MODEL_CONFIG

    next_cursor: str | None = None
    has_more: bool
    limit: int = Field(default=20, ge=1, le=100)


class CollectionEnvelope(Envelope[tuple[DataT, ...]], Generic[DataT]):
    page: CursorPage


class ProblemFieldError(BaseModel):
    model_config = V2_MODEL_CONFIG

    field: NonEmptyString
    code: NonEmptyString
    message: NonEmptyString


class ProblemDetails(BaseModel):
    model_config = V2_MODEL_CONFIG

    type: NonEmptyString
    title: NonEmptyString
    status: int = Field(ge=400, le=599)
    detail: NonEmptyString
    instance: NonEmptyString
    code: NonEmptyString
    request_id: Identifier
    errors: tuple[ProblemFieldError, ...] = ()


class CreateRunRequest(BaseModel):
    model_config = V2_MODEL_CONFIG

    contract_id: Identifier
    execution_mode: ExecutionMode
    parent_run_id: Identifier | None = None
    derivation_kind: DerivationKind = DerivationKind.original
    feedback_ids: tuple[Identifier, ...] = ()
    retry_from_step: Identifier | None = None
    cache_policy: CachePolicy = CachePolicy.fallback_on_recoverable_failure

    @model_validator(mode="after")
    def validate_derivation(self) -> CreateRunRequest:
        if self.derivation_kind is DerivationKind.original and self.parent_run_id is not None:
            raise ValueError("original run must not have parent_run_id")
        if self.derivation_kind is not DerivationKind.original and self.parent_run_id is None:
            raise ValueError("derived run must have parent_run_id")
        if self.retry_from_step is not None and self.derivation_kind is not DerivationKind.retry:
            raise ValueError("retry_from_step is only valid for retry runs")
        return self


class UpdateResearchContractDraftRequest(BaseModel):
    model_config = V2_MODEL_CONFIG

    intent: NonEmptyString | None = None
    contract: ResearchContractInput | None = None

    @model_validator(mode="after")
    def require_change(self) -> UpdateResearchContractDraftRequest:
        if self.intent is None and self.contract is None:
            raise ValueError("draft update must contain intent or contract")
        return self


class ConfirmResearchContractRequest(BaseModel):
    model_config = V2_MODEL_CONFIG

    draft_id: Identifier
    expected_draft_version: int = Field(ge=1)


class SessionStatus(StrEnum):
    active = "active"
    expired = "expired"
    revoked = "revoked"


class SessionQuota(BaseModel):
    model_config = V2_MODEL_CONFIG

    max_projects: int = Field(default=10, ge=1)
    max_runs: int = Field(default=50, ge=1)


class ResearchSession(BaseModel):
    """Public session metadata; the credential and internal id are excluded."""

    model_config = V2_MODEL_CONFIG

    status: SessionStatus
    created_at: UtcDateTime
    expires_at: UtcDateTime
    quota: SessionQuota


class SessionCreated(ResearchSession):
    csrf_token: NonEmptyString
