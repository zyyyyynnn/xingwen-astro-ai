"""Pydantic authoring source for the minimal ``/api`` core contract."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any, ClassVar, Generic, Literal, Self, TypeVar
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SecretStr,
    StringConstraints,
    model_validator,
)

from ._hashing import compute_canonical_payload_hash
from .enums import SourceMode
from .scientific_capabilities import contract_parameters, produced_artifact_kinds


CORE_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
Identifier = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ResearchGoal = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=4, max_length=500),
]
SemanticVersion = Annotated[str, Field(pattern=r"^[1-9]\d*\.\d+\.\d+$")]
ContentHash = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


def _require_chinese(value: str) -> str:
    if not any("\u4e00" <= character <= "\u9fff" for character in value):
        raise ValueError("public analysis must use Simplified Chinese")
    return value


PublicAnalysis = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=12, max_length=500),
    AfterValidator(_require_chinese),
]


def _require_utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("datetime must use UTC")
    return value


UtcDateTime = Annotated[AwareDatetime, AfterValidator(_require_utc)]


class ExecutionMode(StrEnum):
    demo_replay = "demo_replay"
    live = "live"


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
    acquiring_observations = "acquiring_observations"
    analyzing_data = "analyzing_data"
    training_models = "training_models"
    building_visualizations = "building_visualizations"
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
    analysis_report = "analysis_report"
    visualization = "visualization"
    spectrum = "spectrum"
    light_curve = "light_curve"
    model_evaluation = "model_evaluation"
    model_artifact = "model_artifact"
    paper_collection = "paper_collection"
    paper_summary = "paper_summary"
    literature_claims = "literature_claims"
    literature_relations = "literature_relations"
    graph = "graph"
    export = "export"


class ScientificSkillId(StrEnum):
    catalog_crossmatch = "catalog_crossmatch"
    data_profile = "data_profile"
    statistical_analysis = "statistical_analysis"
    correlation_analysis = "correlation_analysis"
    clustering_analysis = "clustering_analysis"
    anomaly_detection = "anomaly_detection"
    chart_visualization = "chart_visualization"
    simbad_lookup = "simbad_lookup"
    skyview_fits = "skyview_fits"
    ephemeris = "ephemeris"
    celestial_events = "celestial_events"
    gaia_cone_search = "gaia_cone_search"
    vizier_tap = "vizier_tap"
    fits_image_analysis = "fits_image_analysis"
    spectrum_analysis = "spectrum_analysis"
    spectrum_acquisition = "spectrum_acquisition"
    light_curve_analysis = "light_curve_analysis"
    light_curve_acquisition = "light_curve_acquisition"
    tabular_machine_learning = "tabular_machine_learning"
    time_series_classification = "time_series_classification"
    time_series_forecast = "time_series_forecast"
    image_classification = "image_classification"
    model_inference = "model_inference"
    wwt_scene = "wwt_scene"


# Scientific output admission derives from the single capability authoring
# source (app.schemas.scientific_capabilities); this module must not re-list
# skill ids in a second capability table.
def _skill_produced_kinds(skill_id: ScientificSkillId) -> frozenset[ArtifactKind]:
    """Artifact kinds one registered skill is authorized to publish."""

    return frozenset(
        ArtifactKind(kind) for kind in produced_artifact_kinds(skill_id.value)
    )


#: Output kinds that require an explicitly authorized scientific skill in the
#: same contract. Data / literature / graph kinds are owned by their own
#: pipeline phases and stay outside this admission.
_SCIENTIFIC_OUTPUT_KINDS = frozenset(
    {
        ArtifactKind.analysis_report,
        ArtifactKind.visualization,
        ArtifactKind.spectrum,
        ArtifactKind.light_curve,
        ArtifactKind.model_evaluation,
        ArtifactKind.model_artifact,
    }
)


class ContractDraftStatus(StrEnum):
    draft = "draft"
    confirmed = "confirmed"
    expired = "expired"


class ModelExecutionStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class ResearchThreadEntryKind(StrEnum):
    user_message = "user_message"
    assistant_message = "assistant_message"
    assistant_reasoning = "assistant_reasoning"
    clarification_question = "clarification_question"
    clarification_answer = "clarification_answer"


class PlannerOutcomeKind(StrEnum):
    clarification_required = "clarification_required"
    draft_ready = "draft_ready"
    partial = "partial"
    unsupported = "unsupported"
    refused = "refused"


class UnitPolicy(StrEnum):
    canonical = "canonical"


class DocumentSourcePolicy(StrEnum):
    """Whether document-derived scientific values may enter the Dataset."""

    disabled = "disabled"
    research_input = "research_input"


class CachePolicy(StrEnum):
    disabled = "disabled"
    fallback_on_recoverable_failure = "fallback_on_recoverable_failure"


class DataRequirements(BaseModel):
    model_config = CORE_MODEL_CONFIG

    unit_policy: UnitPolicy
    document_source_policy: DocumentSourcePolicy


class SourceScope(BaseModel):
    model_config = CORE_MODEL_CONFIG

    allowed_sources: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_sources(self) -> SourceScope:
        if len(self.allowed_sources) != len(set(self.allowed_sources)):
            raise ValueError("allowed_sources must not contain duplicates")
        return self


class PaperSearchScope(BaseModel):
    model_config = CORE_MODEL_CONFIG

    keywords: tuple[NonEmptyString, ...] = ()
    year_from: int | None = Field(default=None, ge=1900, le=2100)
    year_to: int | None = Field(default=None, ge=1900, le=2100)
    source_ids: tuple[Identifier, ...] = ()
    max_candidates: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_year_range(self) -> PaperSearchScope:
        if self.year_from is not None and self.year_to is not None:
            if self.year_from > self.year_to:
                raise ValueError("year_from must not exceed year_to")
        return self


class EvidenceRequirements(BaseModel):
    model_config = CORE_MODEL_CONFIG

    require_locator: bool = True
    require_source_snapshot: bool = True
    minimum_coverage: float = Field(default=1.0, ge=0, le=1)


class QualityConstraints(BaseModel):
    model_config = CORE_MODEL_CONFIG

    source_completeness_min: float = Field(default=1.0, ge=0, le=1)
    unit_consistency_min: float = Field(default=1.0, ge=0, le=1)


class ScientificTaskInput(BaseModel):
    """One bounded invocation of a registered scientific skill."""

    model_config = CORE_MODEL_CONFIG

    task_id: Identifier
    skill_id: ScientificSkillId
    parameters: dict[Identifier, JsonValue] = Field(default_factory=dict)
    input_refs: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def require_bounded_unique_inputs(self) -> ScientificTaskInput:
        if len(self.parameters) > 64:
            raise ValueError("parameters must contain at most 64 entries")
        if len(self.input_refs) != len(set(self.input_refs)):
            raise ValueError("input_refs must not contain duplicates")
        return self


class ResearchContractInput(BaseModel):
    """Shared scientific payload for an editable draft and immutable contract."""

    model_config = CORE_MODEL_CONFIG

    research_goal: ResearchGoal
    target_objects: tuple[Identifier, ...] = Field(min_length=1)
    data_requirements: DataRequirements
    requested_fields: tuple[Identifier, ...] = Field(min_length=1)
    source_scope: SourceScope
    paper_search_scope: PaperSearchScope
    scientific_tasks: tuple[ScientificTaskInput, ...] = ()
    output_requirements: tuple[ArtifactKind, ...] = Field(min_length=1)
    evidence_requirements: EvidenceRequirements
    quality_constraints: QualityConstraints

    @model_validator(mode="after")
    def require_unique_contract_values(self) -> ResearchContractInput:
        for field_name in (
            "target_objects",
            "requested_fields",
            "output_requirements",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must not contain duplicates")
        task_ids = tuple(task.task_id for task in self.scientific_tasks)
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("scientific_tasks must use unique task_id values")
        selected_outputs = frozenset(self.output_requirements)
        support_outputs = frozenset(
            {
                ArtifactKind.field_dictionary,
                ArtifactKind.source_collection,
            }
        )
        if (
            selected_outputs & support_outputs
            and ArtifactKind.dataset not in selected_outputs
        ):
            raise ValueError(
                "field_dictionary and source_collection require dataset output"
            )
        for artifact_kind in _SCIENTIFIC_OUTPUT_KINDS:
            if artifact_kind not in selected_outputs:
                continue
            capable = any(
                artifact_kind in _skill_produced_kinds(task.skill_id)
                for task in self.scientific_tasks
            )
            if not capable:
                raise ValueError(
                    f"{artifact_kind.value} requires an explicitly authorized scientific skill"
                )
        for task in self.scientific_tasks:
            allowed_parameters = {
                name
                for name, _kind, _required, _description in contract_parameters(
                    task.skill_id.value
                )
            }
            unknown_parameters = set(task.parameters) - allowed_parameters
            if unknown_parameters:
                raise ValueError(
                    f"scientific task {task.task_id} contains server-owned or unknown parameters: "
                    + ", ".join(sorted(unknown_parameters))
                )
            missing_parameters = {
                name
                for name, _kind, required, _description in contract_parameters(
                    task.skill_id.value
                )
                if required and name not in task.parameters
            }
            if missing_parameters:
                raise ValueError(
                    f"scientific task {task.task_id} is missing required parameters: "
                    + ", ".join(sorted(missing_parameters))
                )
            if not _skill_produced_kinds(task.skill_id) & selected_outputs:
                raise ValueError(
                    f"scientific task {task.task_id} has no requested output"
                )
        return self


class ResearchThreadSummary(BaseModel):
    """Bounded server-derived Thread facts used by Project navigation reads."""

    model_config = CORE_MODEL_CONFIG

    has_thread_entries: bool
    latest_thread_actor: Literal["user", "assistant", "system"] | None
    has_unanswered_clarification: bool


class ResearchProject(BaseModel):
    model_config = ConfigDict(
        **CORE_MODEL_CONFIG,
        json_schema_extra={
            "examples": [
                {
                    "id": "proj_01JEXAMPLE",
                    "session_id": "sess_01JEXAMPLE",
                    "name": "Exoplanet host-star integration",
                    "description": "Evidence-bound integration for the frozen main case",
                    "case_key": "exoplanet_host_star",
                    "active_draft_id": None,
                    "thread_summary": {
                        "has_thread_entries": False,
                        "latest_thread_actor": None,
                        "has_unanswered_clarification": False,
                    },
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
    active_draft_id: Identifier | None = None
    active_contract_id: Identifier | None = None
    latest_run_id: Identifier | None = None
    latest_run_status: RunStatus | None = None
    latest_run_failure_summary: str | None = None
    thread_summary: ResearchThreadSummary
    created_at: UtcDateTime
    updated_at: UtcDateTime
    revision: int = Field(ge=1)


class ResearchContractDraft(BaseModel):
    model_config = ConfigDict(
        **CORE_MODEL_CONFIG,
        json_schema_extra={
            "examples": [
                {
                    "id": "rcd_01JEXAMPLE",
                    "project_id": "proj_01JEXAMPLE",
                    "session_id": "sess_01JEXAMPLE",
                    "version": 1,
                    "intent": "Integrate exoplanet candidates and host-star parameters",
                    "status": "draft",
                    "contract": {
                        "research_goal": "Integrate exoplanet candidates and host-star parameters",
                        "target_objects": ["exoplanet_candidate", "host_star"],
                        "data_requirements": {
                            "unit_policy": "canonical",
                            "document_source_policy": "disabled",
                        },
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
    project_id: Identifier
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
        **CORE_MODEL_CONFIG,
        json_schema_extra={
            "examples": [
                {
                    "id": "rc_01JEXAMPLE",
                    "project_id": "proj_01JEXAMPLE",
                    "version": 1,
                    "research_goal": "Integrate exoplanet candidates and host-star parameters",
                    "target_objects": ["exoplanet_candidate", "host_star"],
                    "data_requirements": {
                        "unit_policy": "canonical",
                        "document_source_policy": "disabled",
                    },
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


class ResearchThreadEntry(BaseModel):
    """Public, Project-owned entry in the primary Research Thread."""

    model_config = CORE_MODEL_CONFIG

    id: Identifier
    project_id: Identifier
    sequence: int = Field(ge=1)
    kind: ResearchThreadEntryKind
    actor: Literal["user", "assistant", "system"]
    public_content: str
    structured_payload: dict[str, JsonValue] = Field(default_factory=dict)
    model_execution_id: Identifier | None = None
    created_at: UtcDateTime


class ModelExecutionRecord(BaseModel):
    """Pre-run model provenance without raw provider output or private reasoning."""

    model_config = CORE_MODEL_CONFIG

    id: Identifier
    project_id: Identifier
    provider: NonEmptyString
    requested_model: NonEmptyString
    provider_returned_model: str | None = None
    explicit_revision: str | None = None
    prompt_name: NonEmptyString
    prompt_version: SemanticVersion
    prompt_hash: ContentHash
    prompt_snapshot: NonEmptyString
    input_hash: ContentHash | None = None
    input_snapshot: dict[str, JsonValue]
    output_hash: ContentHash | None = None
    output_snapshot: dict[str, JsonValue] | None = None
    parameters_hash: ContentHash
    parameters_snapshot: dict[str, JsonValue]
    status: ModelExecutionStatus
    token_usage: dict[str, JsonValue] | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    provider_request_id: str | None = None
    error_code: str | None = None
    error_summary: str | None = None
    created_at: UtcDateTime
    finished_at: UtcDateTime | None = None


class ResearchCatalogOption(BaseModel):
    """One manifest-backed choice rendered by the Contract authoring UI."""

    model_config = CORE_MODEL_CONFIG

    value: Identifier
    label: NonEmptyString
    description: str = ""
    group: Literal["common", "advanced"] | None = None


class ResearchPlanningCatalog(BaseModel):
    """Project-scoped planning choices derived from current Authorities."""

    model_config = CORE_MODEL_CONFIG

    project_id: Identifier
    case_key: Identifier
    target_objects: tuple[ResearchCatalogOption, ...]
    requested_fields: tuple[ResearchCatalogOption, ...]
    allowed_sources: tuple[ResearchCatalogOption, ...]
    scientific_skills: tuple[ResearchCatalogOption, ...]
    output_requirements: tuple[ResearchCatalogOption, ...]


class PlannerClarificationRequired(BaseModel):
    model_config = CORE_MODEL_CONFIG

    outcome: Literal["clarification_required"]
    public_analysis: PublicAnalysis
    assistant_message: NonEmptyString
    warnings: tuple[NonEmptyString, ...] = ()
    question_id: Identifier
    question: NonEmptyString


class PlannerDraftReady(BaseModel):
    model_config = CORE_MODEL_CONFIG

    outcome: Literal["draft_ready"]
    public_analysis: PublicAnalysis
    assistant_message: NonEmptyString
    warnings: tuple[NonEmptyString, ...] = ()
    contract: ResearchContractInput
    project_title: str | None = Field(default=None, min_length=1, max_length=60)


class PlannerPartial(BaseModel):
    model_config = CORE_MODEL_CONFIG

    outcome: Literal["partial"]
    public_analysis: PublicAnalysis
    assistant_message: NonEmptyString
    warnings: tuple[NonEmptyString, ...] = ()
    missing_information: tuple[NonEmptyString, ...] = Field(min_length=1)


class PlannerUnsupported(BaseModel):
    model_config = CORE_MODEL_CONFIG

    outcome: Literal["unsupported"]
    public_analysis: PublicAnalysis
    assistant_message: NonEmptyString
    warnings: tuple[NonEmptyString, ...] = ()
    reason: NonEmptyString


class PlannerRefused(BaseModel):
    model_config = CORE_MODEL_CONFIG

    outcome: Literal["refused"]
    public_analysis: PublicAnalysis
    assistant_message: NonEmptyString
    warnings: tuple[NonEmptyString, ...] = ()
    reason: NonEmptyString


PlannerOutcome = Annotated[
    PlannerClarificationRequired
    | PlannerDraftReady
    | PlannerPartial
    | PlannerUnsupported
    | PlannerRefused,
    Field(discriminator="outcome"),
]


class ResearchTurnRequest(BaseModel):
    model_config = CORE_MODEL_CONFIG

    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)
    ]
    answer_to_question_id: Identifier | None = None


class ResearchTurnResult(BaseModel):
    model_config = CORE_MODEL_CONFIG

    outcome: PlannerOutcomeKind
    entries: tuple[ResearchThreadEntry, ...]
    active_draft_id: Identifier | None = None
    model_execution_id: Identifier


class RunStepStatus(StrEnum):
    pending = "pending"
    running = "running"
    waiting = "waiting"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    skipped = "skipped"


class RunStepRead(BaseModel):
    model_config = CORE_MODEL_CONFIG

    id: Identifier
    run_id: Identifier
    position: int = Field(ge=0)
    key: Identifier
    label: NonEmptyString
    phase: Identifier
    task_id: Identifier | None = None
    skill_id: ScientificSkillId | None = None
    depends_on_step_keys: tuple[Identifier, ...] = ()
    status: RunStepStatus
    progress: int = Field(ge=0, le=100)
    public_message: str
    started_at: UtcDateTime | None = None
    finished_at: UtcDateTime | None = None
    failure_code: str | None = None


def project_research_contract_input(
    value: ResearchContractInput | ResearchContract | dict[str, Any],
) -> ResearchContractInput:
    """Project a persisted Contract onto its authoritative scientific content."""

    payload = (
        value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    )
    input_payload = {
        field_name: payload[field_name]
        for field_name in ResearchContractInput.model_fields
        if field_name in payload
    }
    return ResearchContractInput.model_validate(input_payload)


def compute_research_contract_content_hash(
    value: ResearchContractInput | ResearchContract | dict[str, Any],
) -> str:
    """Return the production Contract identity over ``ResearchContractInput`` only."""

    contract_input = project_research_contract_input(value)
    return compute_canonical_payload_hash(contract_input.model_dump(mode="json"))


def validate_research_contract_content_hash(
    value: ResearchContract,
) -> ResearchContract:
    """Fail closed when persisted Contract content and identity diverge."""

    expected = compute_research_contract_content_hash(value)
    if value.content_hash != expected:
        raise ValueError(
            f"ResearchContract content_hash does not match ResearchContractInput: {expected}"
        )
    return value


class ResearchRun(BaseModel):
    model_config = ConfigDict(
        **CORE_MODEL_CONFIG,
        json_schema_extra={
            "examples": [
                {
                    "id": "run_01JEXAMPLE",
                    "project_id": "proj_01JEXAMPLE",
                    "contract_id": "rc_01JEXAMPLE",
                    "execution_mode": "live",
                    "status": "queued",
                    "progress": 0,
                    "revision": 1,
                    "parent_run_id": None,
                    "derivation_kind": "original",
                    "retry_from_step": None,
                    "cache_policy": "disabled",
                    "revision_plan_id": None,
                    "feedback_ids": [],
                    "recompute_steps": [],
                    "reused_artifact_version_ids": [],
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
    revision: int = Field(default=1, ge=1)
    parent_run_id: Identifier | None = None
    derivation_kind: DerivationKind
    retry_from_step: Identifier | None = None
    cache_policy: CachePolicy
    revision_plan_id: Identifier | None = None
    feedback_ids: tuple[Identifier, ...] = ()
    recompute_steps: tuple[Identifier, ...] = ()
    reused_artifact_version_ids: tuple[Identifier, ...] = ()
    started_at: UtcDateTime | None = None
    finished_at: UtcDateTime | None = None
    created_at: UtcDateTime
    updated_at: UtcDateTime
    latest_event_sequence: int = Field(default=0, ge=0)
    failure_code: str | None = None
    failure_summary: str | None = None

    @model_validator(mode="after")
    def validate_run_invariants(self) -> ResearchRun:
        if (
            self.derivation_kind is DerivationKind.original
            and self.parent_run_id is not None
        ):
            raise ValueError("original run must not have parent_run_id")
        if (
            self.derivation_kind is not DerivationKind.original
            and self.parent_run_id is None
        ):
            raise ValueError("derived run must have parent_run_id")
        if (
            self.retry_from_step is not None
            and self.derivation_kind is not DerivationKind.retry
        ):
            raise ValueError("retry_from_step is only valid for retry runs")
        has_revision_context = bool(
            self.revision_plan_id and self.feedback_ids and self.recompute_steps
        )
        if self.derivation_kind is DerivationKind.revision and not has_revision_context:
            raise ValueError("revision run requires its confirmed revision context")
        if self.derivation_kind is not DerivationKind.revision and (
            self.revision_plan_id is not None
            or self.feedback_ids
            or self.recompute_steps
            or self.reused_artifact_version_ids
        ):
            raise ValueError("non-revision run must not expose revision context")
        if self.status is RunStatus.completed and self.progress != 100:
            raise ValueError("completed run must have progress 100")
        return self


class RunEvent(BaseModel):
    model_config = ConfigDict(
        **CORE_MODEL_CONFIG,
        json_schema_extra={
            "examples": [
                {
                    "run_id": "run_01JEXAMPLE",
                    "sequence": 1,
                    "activity_id": "run:run_01JEXAMPLE",
                    "activity_kind": "status",
                    "activity_phase": "queued",
                    "activity_name": "研究任务",
                    "step_key": None,
                    "progress": 0,
                    "content": "研究任务已进入执行队列。",
                    "details": {},
                    "artifact_version_ids": [],
                    "occurred_at": "2026-07-21T08:00:00Z",
                }
            ]
        },
    )

    run_id: Identifier
    sequence: int = Field(ge=1)
    activity_id: str = Field(min_length=1, max_length=256)
    activity_kind: Literal[
        "reasoning",
        "tool",
        "observation",
        "status",
        "artifact",
        "retry",
        "error",
        "completion",
    ]
    activity_phase: Literal[
        "queued", "streaming", "running", "completed", "failed", "retrying"
    ]
    activity_name: str = Field(min_length=1, max_length=160)
    step_key: Identifier | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    content: str
    details: dict[str, JsonValue] = Field(default_factory=dict)
    artifact_version_ids: tuple[Identifier, ...] = ()
    occurred_at: UtcDateTime


class RepairEvidenceFact(BaseModel):
    """User-readable evidence for one candidate pair at a repair checkpoint."""

    model_config = CORE_MODEL_CONFIG

    evidence_id: Identifier
    left_candidate_id: Identifier
    right_candidate_id: Identifier
    confidence: float = Field(ge=0, le=1)
    summary: NonEmptyString


class RepairCandidateIdentity(BaseModel):
    """One user-readable canonical identity carried by a repair candidate."""

    model_config = CORE_MODEL_CONFIG

    label: NonEmptyString
    value: NonEmptyString


class RepairCandidateCoordinate(BaseModel):
    model_config = CORE_MODEL_CONFIG

    frame: Literal["ICRS"] = "ICRS"
    right_ascension_degrees: float = Field(ge=0, lt=360)
    declination_degrees: float = Field(ge=-90, le=90)


class RepairCandidateSummary(BaseModel):
    """Domain facts needed to judge a candidate without exposing opaque IDs."""

    model_config = CORE_MODEL_CONFIG

    candidate_id: Identifier
    source_label: NonEmptyString
    entity_label: NonEmptyString
    identities: tuple[RepairCandidateIdentity, ...] = Field(min_length=1)
    coordinate: RepairCandidateCoordinate | None = None


class RepairDefect(BaseModel):
    """One cross-source conflict that cannot be resolved without human authority."""

    model_config = CORE_MODEL_CONFIG

    defect_id: Identifier
    defect_type: Literal["cross_source_conflict"] = "cross_source_conflict"
    logical_match_key: ContentHash
    conflict_code: Identifier
    left_candidates: tuple[RepairCandidateSummary, ...] = Field(min_length=1)
    right_candidates: tuple[RepairCandidateSummary, ...] = Field(min_length=1)
    evidence: tuple[RepairEvidenceFact, ...] = Field(min_length=1)


class RepairRuleSetReference(BaseModel):
    model_config = CORE_MODEL_CONFIG

    rule_set_id: Identifier
    rule_set_version: SemanticVersion
    rule_set_content_hash: ContentHash
    allowed_actions: tuple[Literal["accepted", "rejected", "keep_unresolved"], ...] = (
        "accepted",
        "rejected",
        "keep_unresolved",
    )


class RepairCheckpointContext(BaseModel):
    """Immutable defect and RuleSet facts shown at a scientific repair checkpoint."""

    model_config = CORE_MODEL_CONFIG

    rule_set: RepairRuleSetReference
    source_input_hash: ContentHash
    before_output_hash: ContentHash
    defects: tuple[RepairDefect, ...] = Field(min_length=1)


class RepairDecisionInput(BaseModel):
    model_config = CORE_MODEL_CONFIG

    defect_id: Identifier
    action: Literal["accepted", "rejected", "keep_unresolved"]
    rationale: NonEmptyString = Field(max_length=2000)


class RepairOutcome(BaseModel):
    """Deterministic revalidation closure for one submitted repair batch."""

    model_config = CORE_MODEL_CONFIG

    after_output_hash: ContentHash
    quality_result_hash: ContentHash
    before_evidence_ids: tuple[Identifier, ...]
    after_evidence_ids: tuple[Identifier, ...]
    resolved_defect_ids: tuple[Identifier, ...]
    unresolved_defect_ids: tuple[Identifier, ...]
    status: Literal["revalidated", "false_repair"]


class RunCheckpoint(BaseModel):
    """One human-input request on a Run's ``waiting_for_input`` boundary."""

    model_config = CORE_MODEL_CONFIG

    id: Identifier
    run_id: Identifier
    run_revision: int = Field(ge=1)
    step_key: Identifier
    question: NonEmptyString
    options: tuple[NonEmptyString, ...] = Field(min_length=1)
    kind: Literal["choice", "scientific_repair"] = "choice"
    repair_context: RepairCheckpointContext | None = None
    created_at: UtcDateTime
    selected_option: str | None = None
    free_text: str | None = None
    repair_decisions: tuple[RepairDecisionInput, ...] = ()
    repair_outcome: RepairOutcome | None = None
    decided_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def validate_checkpoint_shape(self) -> Self:
        if self.kind == "scientific_repair":
            if self.repair_context is None or self.selected_option is not None:
                raise ValueError("scientific repair checkpoint requires typed context")
            expected = {item.defect_id for item in self.repair_context.defects}
            decided = {item.defect_id for item in self.repair_decisions}
            if self.repair_decisions and decided != expected:
                raise ValueError(
                    "repair decisions must exactly cover checkpoint defects"
                )
        elif (
            self.repair_context is not None
            or self.repair_decisions
            or self.repair_outcome is not None
        ):
            raise ValueError("choice checkpoint cannot carry scientific repair state")
        return self


class RunCheckpointDecisionRequest(BaseModel):
    """Immutable decision payload for one pending Run checkpoint."""

    model_config = CORE_MODEL_CONFIG

    checkpoint_id: Identifier
    expected_run_revision: int = Field(ge=1)
    selected_option: NonEmptyString | None = None
    free_text: str | None = Field(default=None, max_length=10000)
    repair_decisions: tuple[RepairDecisionInput, ...] = ()

    @model_validator(mode="after")
    def require_one_decision_shape(self) -> Self:
        if (self.selected_option is None) == (not self.repair_decisions):
            raise ValueError(
                "submit either one selected option or typed repair decisions"
            )
        return self


class ResearchArtifact(BaseModel):
    model_config = ConfigDict(
        **CORE_MODEL_CONFIG,
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
    model_config = CORE_MODEL_CONFIG

    type: Literal["pipeline", "model", "algorithm"]
    name: NonEmptyString
    version: NonEmptyString
    model_provider: str | None = None
    requested_model: str | None = None
    provider_returned_model: str | None = None
    explicit_revision: str | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None
    prompt_hash: ContentHash | None = None
    parameters_hash: ContentHash | None = None


class ExportArtifactContent(BaseModel):
    """Canonical export payload; direct provenance is carried only by referenced versions."""

    model_config = CORE_MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    kind: Literal[ArtifactKind.export]
    schema_version: Literal["2.0.0"] = "2.0.0"
    format: Literal["csv", "json", "provenance_report"]
    artifact_version_ids: tuple[Identifier, ...] = Field(min_length=1)

    @property
    def source_snapshot_ids(self) -> tuple[Identifier, ...]:
        return ()

    @property
    def evidence_ids(self) -> tuple[Identifier, ...]:
        return ()

    @model_validator(mode="after")
    def validate_unique_artifact_versions(self) -> ExportArtifactContent:
        normalized_ids: list[str] = []
        for reference in self.artifact_version_ids:
            try:
                normalized_ids.append(str(UUID(reference)))
            except ValueError:
                normalized_ids.append(reference)
        if len(normalized_ids) != len(set(normalized_ids)):
            raise ValueError("Export artifact version references must be unique")
        return self

    def __artifact_publication_is_admitted__(self) -> bool:
        """The exact frozen Export schema is its admission boundary."""

        return type(self) is ExportArtifactContent


class ArtifactVersion(BaseModel):
    model_config = ConfigDict(
        **CORE_MODEL_CONFIG,
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
                        "kind": "export",
                        "format": "json",
                        "artifact_version_ids": [
                            "11111111-1111-4111-8111-111111111111"
                        ],
                    },
                    "content_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "input_hash": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    "source_mode": "live",
                    "producer": {
                        "type": "pipeline",
                        "name": "artifact-export",
                        "version": "1.0.0",
                    },
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
    # Persisted content is an immutable JSON projection. Typed producer
    # candidates own publication validation; this core read contract must not
    # coerce every domain payload into a compact union.
    content: dict[str, JsonValue]
    content_hash: ContentHash
    input_hash: ContentHash
    source_mode: SourceMode
    producer: ProducerReference
    source_snapshot_ids: tuple[Identifier, ...] = ()
    evidence_ids: tuple[Identifier, ...] = ()
    supersedes_version_id: Identifier | None = None
    created_at: UtcDateTime


class ArtifactVersionSummary(BaseModel):
    """Bounded immutable-version reference used by Artifact detail reads."""

    model_config = CORE_MODEL_CONFIG

    id: Identifier
    artifact_id: Identifier
    version_number: int = Field(ge=1)
    schema_version: SemanticVersion
    content_hash: ContentHash
    source_mode: SourceMode
    supersedes_version_id: Identifier | None = None
    created_at: UtcDateTime


class ResearchArtifactDetail(ResearchArtifact):
    """Artifact identity plus stable, bounded version summaries."""

    versions: tuple[ArtifactVersionSummary, ...]


class ProducerExecutionDetail(BaseModel):
    """Reproducible producer metadata with private execution state excluded."""

    model_config = CORE_MODEL_CONFIG

    id: Identifier
    run_id: Identifier
    step_key: Identifier
    step_attempt_id: Identifier
    producer: ProducerReference
    parameters: dict[str, JsonValue]
    parameters_hash: ContentHash
    input_hash: ContentHash
    output_hash: ContentHash | None = None
    status: Literal["running", "completed", "failed", "rejected", "cancelled"]
    started_at: UtcDateTime
    finished_at: UtcDateTime | None = None
    token_usage: dict[str, int] | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    provider_request_id: str | None = Field(default=None, max_length=256)
    error_code: Identifier | None = None


class SourceSnapshotDetail(BaseModel):
    """Reproducible source metadata after the application redaction boundary."""

    model_config = CORE_MODEL_CONFIG

    id: Identifier
    source_id: Identifier
    source_type: Identifier
    retrieved_at: UtcDateTime
    query: JsonValue
    query_hash: ContentHash
    source_version_or_etag: str | None = None
    content_hash: ContentHash
    license_note: NonEmptyString
    cache_version: str | None = None
    request_metadata: dict[str, JsonValue]


class EvidenceDetail(BaseModel):
    """Evidence bound to one immutable version and source snapshot."""

    model_config = CORE_MODEL_CONFIG

    id: Identifier
    artifact_version_id: Identifier
    target_type: Identifier
    target_id: Identifier
    evidence_type: Identifier
    source_snapshot_id: Identifier
    paper_id: Identifier | None = None
    locator: dict[str, JsonValue]
    quote_or_value: JsonValue | None = None
    extraction_method: Identifier
    confidence: float = Field(ge=0, le=1)
    created_at: UtcDateTime


class EvidenceRead(EvidenceDetail):
    """Evidence detail with its immutable, already-redacted source projection."""

    source_snapshot: SourceSnapshotDetail


class ArtifactVersionDetail(ArtifactVersion):
    """Unified immutable content and provenance read projection."""

    content: dict[str, JsonValue]
    producer_execution: ProducerExecutionDetail
    source_snapshots: tuple[SourceSnapshotDetail, ...]
    evidence: tuple[EvidenceDetail, ...]
    quality_projection: dict[str, JsonValue] | None = Field(default=None, exclude=True)
    quality_projection_hash: ContentHash | None = Field(default=None, exclude=True)


class WorkspaceObjectRef(BaseModel):
    """Stable reference to an object shown in the private workspace."""

    model_config = CORE_MODEL_CONFIG

    object_type: Identifier
    object_id: Identifier
    artifact_version_id: Identifier | None = None


class WorkspacePanelSlot(BaseModel):
    """Bounded panel placement without persisting arbitrary window or GPU state."""

    model_config = CORE_MODEL_CONFIG

    slot_id: Identifier
    panel_type: Literal["atlas", "observatory"]
    artifact_version_id: Identifier | None = None
    evidence_id: Identifier | None = None


class AtlasWorkspaceState(BaseModel):
    model_config = CORE_MODEL_CONFIG

    selected_object_ref: WorkspaceObjectRef | None = None
    focus_mode: Identifier | None = None


class ObservatoryWorkspaceState(BaseModel):
    model_config = CORE_MODEL_CONFIG

    active_artifact_version_id: Identifier | None = None
    active_evidence_id: Identifier | None = None


class WorkspaceSnapshotInput(BaseModel):
    """Editable private workspace state accepted by the PUT endpoint."""

    model_config = CORE_MODEL_CONFIG

    active_run_id: Identifier | None = None
    panel_slots: tuple[WorkspacePanelSlot, ...] = Field(default=(), max_length=3)
    selected_object_ref: WorkspaceObjectRef | None = None
    pinned_evidence_ids: tuple[Identifier, ...] = Field(default=(), max_length=100)
    atlas_state: AtlasWorkspaceState = Field(default_factory=AtlasWorkspaceState)
    observatory_state: ObservatoryWorkspaceState = Field(
        default_factory=ObservatoryWorkspaceState
    )
    layout_preset: Identifier

    @model_validator(mode="after")
    def require_unique_workspace_references(self) -> WorkspaceSnapshotInput:
        slot_ids = tuple(slot.slot_id for slot in self.panel_slots)
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("panel_slots must use unique slot_id values")
        if len(self.pinned_evidence_ids) != len(set(self.pinned_evidence_ids)):
            raise ValueError("pinned_evidence_ids must not contain duplicates")
        return self


class WorkspaceSnapshot(WorkspaceSnapshotInput):
    """Private recoverable workspace projection; the session id is never serialized."""

    id: Identifier
    project_id: Identifier
    revision: int = Field(ge=1)
    updated_at: UtcDateTime


class ShareStatus(StrEnum):
    active = "active"
    expired = "expired"
    revoked = "revoked"


class ShareRedactionPolicy(StrEnum):
    redacted_public_snapshot = "redacted_public_snapshot"


class CreateShareSnapshotRequest(BaseModel):
    model_config = CORE_MODEL_CONFIG

    title: NonEmptyString = Field(max_length=200)
    artifact_version_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    evidence_ids: tuple[Identifier, ...] = Field(default=(), max_length=500)
    redaction_policy: Literal[ShareRedactionPolicy.redacted_public_snapshot]
    expires_at: UtcDateTime

    @model_validator(mode="after")
    def require_unique_share_scope(self) -> CreateShareSnapshotRequest:
        for field_name in ("artifact_version_ids", "evidence_ids"):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class ShareSnapshot(BaseModel):
    """Private share metadata. Raw tokens and token hashes are intentionally absent."""

    model_config = CORE_MODEL_CONFIG

    id: Identifier
    project_id: Identifier
    title: NonEmptyString
    artifact_version_ids: tuple[Identifier, ...]
    evidence_ids: tuple[Identifier, ...]
    redaction_policy: ShareRedactionPolicy
    status: ShareStatus
    created_at: UtcDateTime
    expires_at: UtcDateTime
    revoked_at: UtcDateTime | None = None


class ShareSnapshotCreated(ShareSnapshot):
    """One-time creation response containing the only serialized raw share token."""

    share_token: NonEmptyString
    share_url: NonEmptyString


class PublicArtifactVersion(BaseModel):
    """Redacted immutable result projection safe for anonymous presentation."""

    model_config = CORE_MODEL_CONFIG

    id: Identifier
    artifact_id: Identifier
    kind: ArtifactKind
    title: NonEmptyString
    version_number: int = Field(ge=1)
    schema_version: SemanticVersion
    content_hash: ContentHash
    source_mode: SourceMode
    created_at: UtcDateTime
    content: dict[str, JsonValue]
    evidence_ids: tuple[Identifier, ...]


class PublicSourceSnapshot(BaseModel):
    """Public source facts required by the shared Evidence inspector."""

    model_config = CORE_MODEL_CONFIG

    source_id: NonEmptyString
    source_type: NonEmptyString
    retrieved_at: UtcDateTime
    license_note: NonEmptyString
    request_metadata: dict[str, JsonValue]


class PublicEvidence(BaseModel):
    """Redacted Evidence detail frozen with a shared immutable result."""

    model_config = CORE_MODEL_CONFIG

    id: Identifier
    artifact_version_id: Identifier
    source_snapshot_id: Identifier
    locator: dict[str, JsonValue]
    quote_or_value: JsonValue
    created_at: UtcDateTime
    source: PublicSourceSnapshot


class PublicShareSnapshot(BaseModel):
    """Anonymous read-only projection frozen when the share is created."""

    model_config = CORE_MODEL_CONFIG

    id: Identifier
    title: NonEmptyString
    artifact_versions: tuple[PublicArtifactVersion, ...]
    evidence: tuple[PublicEvidence, ...]
    redaction_policy: ShareRedactionPolicy
    created_at: UtcDateTime
    expires_at: UtcDateTime


class ResponseMeta(BaseModel):
    model_config = CORE_MODEL_CONFIG

    request_id: Identifier
    schema_version: Literal["2.0.0"] = "2.0.0"
    generated_at: UtcDateTime


class ResponseLinks(BaseModel):
    model_config = CORE_MODEL_CONFIG

    self: NonEmptyString


DataT = TypeVar("DataT")


class Envelope(BaseModel, Generic[DataT]):
    model_config = CORE_MODEL_CONFIG

    data: DataT
    meta: ResponseMeta
    links: ResponseLinks


class CursorPage(BaseModel):
    model_config = CORE_MODEL_CONFIG

    next_cursor: str | None = None
    has_more: bool
    limit: int = Field(default=20, ge=1, le=100)


class CollectionEnvelope(Envelope[tuple[DataT, ...]], Generic[DataT]):
    page: CursorPage


class ProblemFieldError(BaseModel):
    model_config = CORE_MODEL_CONFIG

    field: NonEmptyString
    code: NonEmptyString
    message: NonEmptyString


class ProblemDetails(BaseModel):
    model_config = CORE_MODEL_CONFIG

    type: NonEmptyString
    title: NonEmptyString
    status: int = Field(ge=400, le=599)
    detail: NonEmptyString
    instance: NonEmptyString
    code: NonEmptyString
    request_id: Identifier
    errors: tuple[ProblemFieldError, ...] = ()


class CreateRunRequest(BaseModel):
    model_config = CORE_MODEL_CONFIG

    contract_id: Identifier
    execution_mode: ExecutionMode


class UpdateResearchContractDraftRequest(BaseModel):
    model_config = CORE_MODEL_CONFIG

    intent: NonEmptyString | None = None
    contract: ResearchContractInput | None = None

    @model_validator(mode="after")
    def require_change(self) -> UpdateResearchContractDraftRequest:
        if self.intent is None and self.contract is None:
            raise ValueError("draft update must contain intent or contract")
        return self


class CreateResearchProjectRequest(BaseModel):
    """Minimal project creation payload; `case_key` stays frozen to the main case."""

    model_config = CORE_MODEL_CONFIG

    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    description: str = Field(default="", max_length=2000)
    case_key: Literal["exoplanet_host_star"]


class UpdateResearchProjectRequest(BaseModel):
    model_config = CORE_MODEL_CONFIG

    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


class CreateResearchContractDraftRequest(BaseModel):
    """Creates an editable draft bound to a session-owned project.

    The draft never carries `execution_mode`; that field belongs exclusively
    to Run creation.
    """

    model_config = CORE_MODEL_CONFIG

    intent: NonEmptyString
    contract: ResearchContractInput


class ConfirmResearchContractRequest(BaseModel):
    model_config = CORE_MODEL_CONFIG

    draft_id: Identifier
    expected_draft_version: int = Field(ge=1)


class SessionStatus(StrEnum):
    active = "active"
    expired = "expired"
    revoked = "revoked"


class SessionQuota(BaseModel):
    model_config = CORE_MODEL_CONFIG

    max_projects: int = Field(default=10, ge=1)
    max_runs: int = Field(default=50, ge=1)


class ResearchSession(BaseModel):
    """Public session metadata; the credential and internal id are excluded."""

    model_config = CORE_MODEL_CONFIG

    status: SessionStatus
    created_at: UtcDateTime
    expires_at: UtcDateTime
    quota: SessionQuota


class SessionCreated(ResearchSession):
    csrf_token: NonEmptyString


class ModelProviderPreset(StrEnum):
    dashscope = "dashscope"
    custom = "custom"


class ModelProviderConfigurationSource(StrEnum):
    deployment = "deployment"
    workspace = "workspace"


class ModelProviderConfigurationStatus(BaseModel):
    """Write-only credentials are represented only by a non-secret suffix hint."""

    model_config = CORE_MODEL_CONFIG

    status: Literal["unconfigured", "ready"]
    revision: int = Field(ge=0)
    source: ModelProviderConfigurationSource | None
    preset: ModelProviderPreset | None
    base_url: str | None
    dashscope_base_url: str
    model: str | None
    api_key_hint: str | None
    verified_at: UtcDateTime | None
    updated_at: UtcDateTime | None
    editable: bool


class ConfigureModelProviderRequest(BaseModel):
    """Configure and verify the instance-wide Chat Completions provider."""

    model_config = CORE_MODEL_CONFIG

    preset: ModelProviderPreset
    base_url: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    ] = None
    model: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    api_key: SecretStr = Field(
        min_length=1,
        max_length=2048,
        json_schema_extra={"writeOnly": True},
    )


__all__ = ["PlannerOutcome"]
