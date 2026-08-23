"""Shared publication lifecycle, provenance and binding support for Run steps.

This module owns the single ProducerExecution lifecycle used by every
specialized step service:

    StepAttempt starts
    -> build the current ProducerExecutionRequest
    -> ProducerExecutionStore.start_producer_execution
    -> actual scientific/model operation
    -> ProducerExecutionStore.finish_producer_execution
    -> Publisher receives the persisted ProducerExecution identity
    -> ArtifactVersion is published
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import SourceSnapshotModel
from app.schemas.core import ResearchContract
from app.schemas.enums import SourceMode
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.crossmatch import CrossmatchSourceInput
from app.schemas.data_artifacts import (
    DataArtifactBuildResult,
    DatasetArtifactCandidate,
    SourceTableArtifactAuthority,
)
from app.schemas.literature_claim import LiteratureClaimsCandidate
from app.schemas.literature_relation import LiteratureRelationsCandidate
from app.schemas.paper_collection import PaperCollection
from app.schemas.paper_summary import PaperSummaryArtifactContent
from app.services.model_execution import (
    ModelToolCall,
    ModelExecutionError,
    ModelExecutionPort,
    ModelExecutionRequest,
    ModelExecutionResponse,
)
from app.workflow.publisher import (
    AdmittedArtifactCandidate,
    ArtifactEvidenceBinding,
    ArtifactPublication,
    ArtifactSourceSnapshotBinding,
    ProducerExecutionConflictError,
    ProducerExecutionRequest,
    ProducerExecutionSnapshot,
    ProducerExecutionStore,
)
from app.workflow.store import AttemptHandle, LeaseGrant
from packages.prompts.registry import PromptRegistry, PromptRecord
from services.data_pipeline.revision import DataRevisionExecutionInput


_SUPERSEDES_UNSET = object()


def step_uuid(namespace_seed: str, name: str) -> UUID:
    return uuid5(uuid5(NAMESPACE_URL, namespace_seed), name)


def _declared_input_hash(content: dict[str, object]) -> str:
    """Return the candidate's declared input_hash for ProducerExecution binding.

    The Publisher binds the persisted ProducerExecution to the admitted
    candidate through the exact declared input hash. Export candidates do not
    declare one and are exempt from input-hash matching, so a canonical
    placeholder is used to keep the ledger hash format valid.
    """
    declared = content.get("input_hash")
    if isinstance(declared, str):
        return declared
    return "sha256:" + "0" * 64


@dataclass(slots=True)
class RunStepContext:
    run_id: UUID
    project_id: UUID
    session_id: str
    contract: ResearchContract
    artifacts: dict[str, UUID]
    versions: dict[str, UUID]
    data_acquisitions: tuple[CrossmatchSourceInput, CrossmatchSourceInput] | None = None
    data_result: DataArtifactBuildResult | None = None
    data_revision: DataRevisionExecutionInput | None = None
    paper_collection: PaperCollection | None = None
    paper_summary: PaperSummaryArtifactContent | None = None
    literature_claims: LiteratureClaimsCandidate | None = None
    literature_relations: LiteratureRelationsCandidate | None = None


@dataclass(frozen=True, slots=True)
class PreparedStep:
    publications: tuple[ArtifactPublication, ...]
    # Activity/result fact used by RunEvent and step progress projections.
    activity_result_summary: str
    # Separate user-facing Assistant Message; never reuse the Activity text.
    assistant_narrative: str | None = None
    activity_id: str | None = None
    activity_name: str | None = None


class StepPublicationFactory:
    """Own the step-scoped ProducerExecution ledger and publication binding."""

    def __init__(
        self,
        *,
        factory: Callable[[], Session],
        executions: ProducerExecutionStore | None = None,
    ) -> None:
        self._factory = factory
        self._executions = executions or ProducerExecutionStore(factory)

    def start_producer(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        operation_key: str,
        producer_type: str,
        producer_name: str,
        producer_version: str,
        input_hash: str,
        parameters: dict[str, str | int | float | bool],
        attempt: AttemptHandle,
        lease: LeaseGrant,
        parameters_hash: str | None = None,
        model_provider: str | None = None,
        requested_model: str | None = None,
        explicit_revision: str | None = None,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
        prompt_hash: str | None = None,
        authorized_tool_name: str | None = None,
        authorized_skill_id: str | None = None,
        registry_revision: str | None = None,
    ) -> ProducerExecutionSnapshot:
        return self._executions.start_producer_execution(
            ProducerExecutionRequest(
                run_id=context.run_id,
                step_key=step_key,
                attempt_id=attempt.attempt_id,
                idempotency_key=(
                    f"run:{context.run_id}:step:{step_key}:"
                    f"attempt:{attempt.attempt_number}:producer:{operation_key}"
                ),
                producer_type=producer_type,
                producer_name=producer_name,
                producer_version=producer_version,
                input_hash=input_hash,
                parameters=parameters,
                parameters_hash=parameters_hash,
                model_provider=model_provider,
                requested_model=requested_model,
                explicit_revision=explicit_revision,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                prompt_hash=prompt_hash,
                authorized_tool_name=authorized_tool_name,
                authorized_skill_id=authorized_skill_id,
                registry_revision=registry_revision,
            ),
            token=lease.token,
            generation=lease.generation,
            expected_status=attempt.run_status,
            expected_revision=attempt.run_revision,
        )

    def finish_producer(
        self,
        execution_id: UUID,
        *,
        status: str,
        output_hash: str | None = None,
        input_hash: str | None = None,
        response: ModelExecutionResponse | None = None,
        error_code: str | None = None,
        tool_call_id: str | None = None,
        validated_arguments_hash: str | None = None,
        rejected_arguments_hash: str | None = None,
        error_hash: str | None = None,
        public_message: str | None = None,
    ) -> ProducerExecutionSnapshot:
        return self._executions.finish_producer_execution(
            execution_id,
            status=status,
            output_hash=output_hash,
            input_hash=input_hash,
            token_usage=response.token_usage if response is not None else None,
            latency_ms=response.latency_ms if response is not None else None,
            provider_returned_model=(
                response.provider_returned_model if response is not None else None
            ),
            provider_request_id=(
                response.provider_request_id if response is not None else None
            ),
            error_code=error_code,
            tool_call_id=tool_call_id,
            validated_arguments_hash=validated_arguments_hash,
            rejected_arguments_hash=rejected_arguments_hash,
            error_hash=error_hash,
            public_message=public_message,
            model_response=(
                {
                    "payload": dict(response.payload),
                    "tool_calls": [
                        {
                            "id": item.id,
                            "name": item.name,
                            "arguments": dict(item.arguments),
                        }
                        for item in response.tool_calls
                    ],
                }
                if response is not None
                else None
            ),
        )

    def find_completed_model(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        request: ModelExecutionRequest,
        producer_name: str,
        producer_version: str,
        attempt: AttemptHandle,
    ) -> ProducerExecutionSnapshot | None:
        """Find an exact completed child call from an earlier step attempt."""

        return self._executions.find_completed_model_execution(
            ProducerExecutionRequest(
                run_id=context.run_id,
                step_key=step_key,
                attempt_id=attempt.attempt_id,
                idempotency_key="completed-model-replay-lookup",
                producer_type="model",
                producer_name=producer_name,
                producer_version=producer_version,
                input_hash=request.input_hash,
                parameters={
                    key: value
                    for key, value in request.parameters.items()
                    if isinstance(value, (str, int, float, bool))
                },
                parameters_hash=request.parameters_hash,
                model_provider=request.provider,
                requested_model=request.requested_model,
                explicit_revision=request.explicit_revision,
                prompt_name=request.prompt_name,
                prompt_version=request.prompt_version,
                prompt_hash=request.prompt_hash,
            )
        )

    def publication(
        self,
        context: RunStepContext,
        *,
        kind: str,
        candidate: AdmittedArtifactCandidate,
        producer_execution_id: UUID,
        artifact_id: UUID | None = None,
        version_id: UUID | None = None,
        supersedes_version_id: UUID | None | object = _SUPERSEDES_UNSET,
        source_mode: SourceMode = SourceMode.live,
    ) -> ArtifactPublication:
        artifact_id = artifact_id or context.artifacts[kind]
        version_id = version_id or step_uuid(
            str(context.run_id), f"artifact-version:{kind}"
        )
        supersedes = (
            context.versions.get(kind)
            if supersedes_version_id is _SUPERSEDES_UNSET
            else cast(UUID | None, supersedes_version_id)
        )
        return ArtifactPublication(
            artifact_id=artifact_id,
            publication_key=f"run:{context.run_id}:artifact:{kind}",
            producer_execution_id=producer_execution_id,
            candidate=candidate,
            source_mode=SourceMode(source_mode),
            supersedes_version_id=supersedes,
            version_id=version_id,
        )

    def _producer_parameters(
        self, producer: object
    ) -> dict[str, str | int | float | bool]:
        """Record the producer's declared scalar metadata as its parameter set."""
        if hasattr(producer, "model_dump"):
            raw = producer.model_dump(mode="json")
        else:
            raw = dict(vars(producer))
        parameters: dict[str, str | int | float | bool] = {}
        for key, value in raw.items():
            if value is None or not isinstance(value, (str, int, float, bool)):
                continue
            if isinstance(value, str) and len(value) > 256:
                continue
            parameters[key] = value
        return parameters

    def ensure_source_snapshots(
        self,
        context: RunStepContext,
        snapshots: tuple[object, ...] | list[object],
    ) -> None:
        with self._factory() as session, session.begin():
            for source in snapshots:
                snapshot_id = step_uuid(
                    str(context.project_id),
                    f"source-snapshot:{source.snapshot_id}",
                )
                existing = session.get(SourceSnapshotModel, snapshot_id)
                if existing is not None:
                    continue
                session.add(
                    SourceSnapshotModel(
                        id=snapshot_id,
                        project_id=context.project_id,
                        source_id=source.source_id,
                        source_type=source.source_type,
                        retrieved_at=source.retrieved_at,
                        query=source.query,
                        query_hash=source.query_hash,
                        source_version_or_etag=source.source_version_or_etag,
                        content_hash=source.content_hash,
                        license_note=source.license_note,
                        cache_version=source.cache_version,
                        request_metadata=source.request_metadata,
                    )
                )

    def persisted_snapshot_id(self, context: RunStepContext, pipeline_id: str) -> str:
        return str(step_uuid(str(context.project_id), f"source-snapshot:{pipeline_id}"))

    def source_bindings(
        self,
        context: RunStepContext,
        pipeline_ids: tuple[str, ...],
    ) -> tuple[ArtifactSourceSnapshotBinding, ...]:
        return tuple(
            ArtifactSourceSnapshotBinding(
                pipeline_source_snapshot_id=item,
                persisted_source_snapshot_id=self.persisted_snapshot_id(context, item),
            )
            for item in pipeline_ids
        )

    def paper_summary_bindings(
        self,
        context: RunStepContext,
        summary: PaperSummaryArtifactContent,
        *,
        source_snapshots_are_persisted: bool = False,
    ) -> tuple[
        tuple[ArtifactSourceSnapshotBinding, ...],
        tuple[ArtifactEvidenceBinding, ...],
    ]:
        source_bindings = (
            tuple(
                ArtifactSourceSnapshotBinding(
                    pipeline_source_snapshot_id=item,
                    persisted_source_snapshot_id=item,
                )
                for item in summary.source_snapshot_ids
            )
            if source_snapshots_are_persisted
            else self.source_bindings(context, summary.source_snapshot_ids)
        )
        evidence_bindings = tuple(
            ArtifactEvidenceBinding(
                target_type="evidence",
                target_id=item.evidence_id,
                pipeline_evidence_id=item.evidence_id,
                pipeline_source_snapshot_id=item.source_snapshot_id,
                persisted_evidence_id=str(
                    step_uuid(
                        str(context.run_id),
                        f"paper_summary:evidence:{item.evidence_id}",
                    )
                ),
                persisted_source_snapshot_id=(
                    item.source_snapshot_id
                    if source_snapshots_are_persisted
                    else self.persisted_snapshot_id(context, item.source_snapshot_id)
                ),
            )
            for item in summary.evidence
        )
        return source_bindings, evidence_bindings

    def data_bindings(
        self,
        context: RunStepContext,
        *,
        kind: str,
        candidate: DatasetArtifactCandidate,
        snapshot_bindings_override: dict[str, str] | None = None,
    ) -> tuple[
        tuple[ArtifactSourceSnapshotBinding, ...],
        tuple[ArtifactEvidenceBinding, ...],
    ]:
        """Bind pipeline snapshot identities to persisted SourceSnapshot rows.

        Structured left/right snapshots are derived through the deterministic
        run-scoped uuid; callers may supply exact overrides for snapshots that
        already exist as persisted rows (document research inputs), which must
        never be duplicated by ``ensure_source_snapshots``.
        """

        overrides = snapshot_bindings_override or {}

        def persisted_id(pipeline_snapshot_id: str) -> str:
            bound = overrides.get(pipeline_snapshot_id)
            if bound is not None:
                return str(bound)
            if isinstance(candidate.authority, SourceTableArtifactAuthority):
                if pipeline_snapshot_id == candidate.authority.source_snapshot_id:
                    return str(pipeline_snapshot_id)
            return self.persisted_snapshot_id(context, pipeline_snapshot_id)

        snapshots = tuple(
            ArtifactSourceSnapshotBinding(
                pipeline_source_snapshot_id=item,
                persisted_source_snapshot_id=persisted_id(item),
            )
            for item in candidate.source_snapshot_ids
        )
        transformations = {
            item.evidence_id: item for item in candidate.transformation_evidence
        }
        crossmatch = {
            item.evidence_id: item
            for item in getattr(candidate.authority, "evidence", ())
        }
        evidence: list[ArtifactEvidenceBinding] = []
        for pipeline_id in candidate.evidence_ids:
            transformation = transformations.get(pipeline_id)
            if transformation is not None:
                target_type = "canonical_field"
                target_id = transformation.canonical_field_id
                pipeline_snapshot_id = transformation.locator.source_snapshot_id
            else:
                item = crossmatch[pipeline_id]
                pipeline_snapshot_id = next(
                    iter({value.source_snapshot_id for value in item.left_locators})
                )
                target_type = "crossmatch"
                target_id = pipeline_id
            evidence.append(
                ArtifactEvidenceBinding(
                    target_type=target_type,
                    target_id=target_id,
                    pipeline_evidence_id=pipeline_id,
                    pipeline_source_snapshot_id=pipeline_snapshot_id,
                    persisted_evidence_id=str(
                        step_uuid(
                            str(context.run_id),
                            f"{kind}:evidence:{pipeline_id}",
                        )
                    ),
                    persisted_source_snapshot_id=persisted_id(
                        pipeline_snapshot_id
                    ),
                )
            )
        return snapshots, tuple(evidence)

    def literature_bindings(
        self,
        context: RunStepContext,
        *,
        kind: str,
        candidate: BaseModel,
    ) -> tuple[ArtifactEvidenceBinding, ...]:
        bindings: dict[tuple[str, str, str, str], ArtifactEvidenceBinding] = {}
        for reference in getattr(candidate, "evidence_references", ()):
            targets = (
                (("claim", reference.claim_id),)
                if kind == "literature_claims"
                else (
                    ("claim", reference.claim_id),
                    ("relation", reference.relation_id),
                )
            )
            for target_type, target_id in targets:
                key = (
                    target_type,
                    target_id,
                    reference.evidence_id,
                    reference.source_snapshot_id,
                )
                bindings.setdefault(
                    key,
                    ArtifactEvidenceBinding(
                        target_type=target_type,
                        target_id=target_id,
                        pipeline_evidence_id=reference.evidence_id,
                        pipeline_source_snapshot_id=reference.source_snapshot_id,
                        persisted_evidence_id=str(
                            step_uuid(
                                str(context.run_id),
                                f"{kind}:evidence:{':'.join(key)}",
                            )
                        ),
                        persisted_source_snapshot_id=self.persisted_snapshot_id(
                            context,
                            reference.source_snapshot_id,
                        ),
                    ),
                )
        return tuple(bindings[key] for key in sorted(bindings))


class TrackedStepModelExecutionPort:
    """Persist Qwen execution facts before the provider request is issued."""

    def __init__(
        self,
        *,
        base: ModelExecutionPort,
        publications: StepPublicationFactory,
        context: RunStepContext,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> None:
        self._base = base
        self._publications = publications
        self._context = context
        self._step_key = step_key
        self._attempt = attempt
        self._lease = lease

    def start(
        self, request: ModelExecutionRequest
    ) -> tuple[ModelExecutionResponse, UUID]:
        return self.start_named(
            request,
            producer_name=f"{request.provider}-chat-completions",
            producer_version=request.explicit_revision or request.requested_model,
        )

    def start_named(
        self,
        request: ModelExecutionRequest,
        *,
        producer_name: str,
        producer_version: str,
        resume_completed: bool = False,
    ) -> tuple[ModelExecutionResponse, UUID]:
        if resume_completed:
            completed = self._publications.find_completed_model(
                self._context,
                step_key=self._step_key,
                request=request,
                producer_name=producer_name,
                producer_version=producer_version,
                attempt=self._attempt,
            )
            if completed is not None:
                return _replayed_model_response(completed), completed.id
        execution = self._publications.start_producer(
            self._context,
            step_key=self._step_key,
            operation_key=(
                f"model:{producer_name}:{request.prompt_name}:"
                f"{request.input_hash[-12:]}"
            ),
            producer_type="model",
            producer_name=producer_name,
            producer_version=producer_version,
            input_hash=request.input_hash,
            parameters={
                key: value
                for key, value in request.parameters.items()
                if isinstance(value, (str, int, float, bool))
            },
            parameters_hash=request.parameters_hash,
            model_provider=request.provider,
            requested_model=request.requested_model,
            explicit_revision=request.explicit_revision,
            prompt_name=request.prompt_name,
            prompt_version=request.prompt_version,
            prompt_hash=request.prompt_hash,
            attempt=self._attempt,
            lease=self._lease,
        )
        if execution.replayed:
            return _replayed_model_response(execution), execution.id
        try:
            response = self._base.execute(request)
        except ModelExecutionError as error:
            self._publications.finish_producer(
                execution.id,
                status="failed",
                output_hash=error.output_hash,
                response=(
                    ModelExecutionResponse(
                        payload={},
                        output_hash=error.output_hash or ("sha256:" + "0" * 64),
                        token_usage=error.token_usage,
                        latency_ms=error.latency_ms or 0,
                        provider_request_id=error.provider_request_id,
                    )
                    if error.latency_ms is not None
                    or error.token_usage is not None
                    or error.provider_request_id is not None
                    else None
                ),
                error_code=error.code,
            )
            raise
        except Exception:
            self._publications.finish_producer(
                execution.id,
                status="failed",
                error_code="MODEL_EXECUTION_FAILED",
            )
            raise
        return response, execution.id

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        response, execution_id = self.start(request)
        self._publications.finish_producer(
            execution_id,
            status="completed",
            output_hash=response.output_hash,
            response=response,
        )
        return response

    def execute_resumable(
        self, request: ModelExecutionRequest
    ) -> ModelExecutionResponse:
        """Replay exact completed child calls across step attempts."""

        response, execution_id = self.start_named(
            request,
            producer_name=f"{request.provider}-chat-completions",
            producer_version=request.explicit_revision or request.requested_model,
            resume_completed=True,
        )
        self._publications.finish_producer(
            execution_id,
            status="completed",
            output_hash=response.output_hash,
            response=response,
        )
        return response

    def start_agent_call(
        self,
        request: ModelExecutionRequest,
        *,
        authorized_tool_name: str,
        authorized_skill_id: str,
        registry_revision: str,
    ) -> tuple[ModelExecutionResponse, UUID]:
        """Persist the governed function-call producer before the provider call."""

        execution = self._publications.start_producer(
            self._context,
            step_key=self._step_key,
            operation_key=f"agent:{request.prompt_name}:{request.input_hash[-12:]}",
            producer_type="model",
            producer_name="research_step_agent",
            producer_version=request.explicit_revision or request.requested_model,
            input_hash=request.input_hash,
            parameters={
                key: value
                for key, value in request.parameters.items()
                if isinstance(value, (str, int, float, bool))
            },
            parameters_hash=request.parameters_hash,
            model_provider=request.provider,
            requested_model=request.requested_model,
            explicit_revision=request.explicit_revision,
            prompt_name=request.prompt_name,
            prompt_version=request.prompt_version,
            prompt_hash=request.prompt_hash,
            authorized_tool_name=authorized_tool_name,
            authorized_skill_id=authorized_skill_id,
            registry_revision=registry_revision,
            attempt=self._attempt,
            lease=self._lease,
        )
        if execution.replayed:
            return _replayed_model_response(execution), execution.id
        try:
            response = self._base.execute(request)
        except ModelExecutionError as error:
            self._publications.finish_producer(
                execution.id,
                status="failed",
                output_hash=error.output_hash,
                response=(
                    ModelExecutionResponse(
                        payload={},
                        output_hash=error.output_hash or ("sha256:" + "0" * 64),
                        token_usage=error.token_usage,
                        latency_ms=error.latency_ms or 0,
                        provider_request_id=error.provider_request_id,
                    )
                    if error.latency_ms is not None
                    or error.token_usage is not None
                    or error.provider_request_id is not None
                    else None
                ),
                error_code=error.code,
                error_hash=compute_canonical_payload_hash({"error": error.code}),
            )
            raise
        except Exception:
            self._publications.finish_producer(
                execution.id,
                status="failed",
                error_code="AGENT_MODEL_EXECUTION_FAILED",
                error_hash=compute_canonical_payload_hash(
                    {"error": "AGENT_MODEL_EXECUTION_FAILED"}
                ),
            )
            raise
        return response, execution.id

    def complete_agent_call(
        self,
        execution_id: UUID,
        *,
        response: ModelExecutionResponse,
        tool_call_id: str,
        validated_arguments_hash: str,
        public_message: str,
    ) -> None:
        self._publications.finish_producer(
            execution_id,
            status="completed",
            output_hash=response.output_hash,
            response=response,
            tool_call_id=tool_call_id,
            validated_arguments_hash=validated_arguments_hash,
            public_message=public_message,
        )

    def reject_agent_call(
        self,
        execution_id: UUID,
        *,
        error_code: str,
        error_hash: str,
        response: ModelExecutionResponse | None = None,
        tool_call_id: str | None = None,
        rejected_arguments_hash: str | None = None,
    ) -> None:
        self._publications.finish_producer(
            execution_id,
            status="rejected",
            output_hash=response.output_hash if response is not None else None,
            response=response,
            error_code=error_code,
            tool_call_id=tool_call_id,
            rejected_arguments_hash=rejected_arguments_hash,
            error_hash=error_hash,
        )

    def complete(
        self,
        execution_id: UUID,
        *,
        input_hash: str,
        output_hash: str,
        response: ModelExecutionResponse,
    ) -> None:
        self._publications.finish_producer(
            execution_id,
            status="completed",
            input_hash=input_hash,
            output_hash=output_hash,
            response=response,
        )

    def reject(
        self,
        execution_id: UUID,
        *,
        input_hash: str | None,
        response: ModelExecutionResponse,
        error_code: str,
    ) -> None:
        self._publications.finish_producer(
            execution_id,
            status="rejected",
            input_hash=input_hash,
            output_hash=response.output_hash,
            response=response,
            error_code=error_code,
        )


def _replayed_model_response(
    execution: ProducerExecutionSnapshot,
) -> ModelExecutionResponse:
    stored = execution.model_response
    if (
        execution.status != "completed"
        or stored is None
        or execution.output_hash is None
        or execution.latency_ms is None
    ):
        raise ProducerExecutionConflictError(
            "model execution cannot replay an incomplete provider response"
        )
    payload = stored.get("payload")
    raw_tool_calls = stored.get("tool_calls")
    if not isinstance(payload, dict) or not isinstance(raw_tool_calls, list):
        raise ProducerExecutionConflictError(
            "persisted model response does not match the replay contract"
        )
    tool_calls: list[ModelToolCall] = []
    for raw in raw_tool_calls:
        if not isinstance(raw, dict):
            raise ProducerExecutionConflictError(
                "persisted model tool call is malformed"
            )
        call_id = raw.get("id")
        name = raw.get("name")
        arguments = raw.get("arguments")
        if (
            not isinstance(call_id, str)
            or not isinstance(name, str)
            or not isinstance(arguments, dict)
        ):
            raise ProducerExecutionConflictError(
                "persisted model tool call is incomplete"
            )
        tool_calls.append(ModelToolCall(call_id, name, dict(arguments)))
    return ModelExecutionResponse(
        payload=dict(payload),
        output_hash=execution.output_hash,
        token_usage=(
            dict(execution.token_usage) if execution.token_usage is not None else None
        ),
        latency_ms=execution.latency_ms,
        provider_request_id=execution.provider_request_id,
        provider_returned_model=execution.provider_returned_model,
        tool_calls=tuple(tool_calls),
    )


class ResumableStepModelExecutionPort:
    """Model port that reuses exact completed child calls across attempts."""

    def __init__(self, tracked: TrackedStepModelExecutionPort) -> None:
        self._tracked = tracked

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        return self._tracked.execute_resumable(request)


class StepModelCaller:
    """Execute one governed artifact-producing model call for a Run step."""

    def __init__(
        self,
        *,
        model_port: TrackedStepModelExecutionPort,
        provider: str,
        requested_model: str,
        explicit_revision: str | None,
        prompts: PromptRegistry,
    ) -> None:
        self._model_port = model_port
        self._provider = provider
        self._requested_model = requested_model
        self._explicit_revision = explicit_revision
        self._prompts = prompts

    @property
    def requested_model(self) -> str:
        return self._requested_model

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def explicit_revision(self) -> str | None:
        return self._explicit_revision

    def prompt(self, name: str) -> PromptRecord:
        return self._prompts.get(name)

    def execute_json(
        self,
        *,
        prompt_name: str,
        input_payload: dict[str, object],
        parameters: dict[str, float | int],
        producer_name: str | None = None,
        producer_version: str | None = None,
    ) -> tuple[str, ModelExecutionResponse, UUID]:
        prompt = self._prompts.get(prompt_name)
        request = ModelExecutionRequest(
            provider=self._provider,
            requested_model=self._requested_model,
            explicit_revision=self._explicit_revision,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            prompt_hash=prompt.content_hash,
            prompt=prompt.content,
            input_payload=dict(input_payload),
            parameters=dict(parameters),
            response_mode="json",
            enable_thinking=False,
        )
        response, execution_id = (
            self._model_port.start_named(
                request,
                producer_name=producer_name,
                producer_version=producer_version,
            )
            if producer_name is not None and producer_version is not None
            else self._model_port.start(request)
        )
        model_response = json.dumps(
            response.payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return model_response, response, execution_id

    def complete(
        self,
        execution_id: UUID,
        *,
        input_hash: str,
        output_hash: str,
        response: ModelExecutionResponse,
    ) -> None:
        self._model_port.complete(
            execution_id,
            input_hash=input_hash,
            output_hash=output_hash,
            response=response,
        )

    def reject(
        self,
        execution_id: UUID,
        *,
        input_hash: str | None,
        response: ModelExecutionResponse,
        error_code: str,
    ) -> None:
        self._model_port.reject(
            execution_id,
            input_hash=input_hash,
            response=response,
            error_code=error_code,
        )


__all__ = [
    "PreparedStep",
    "ResumableStepModelExecutionPort",
    "RunStepContext",
    "StepModelCaller",
    "StepPublicationFactory",
    "TrackedStepModelExecutionPort",
    "step_uuid",
]
