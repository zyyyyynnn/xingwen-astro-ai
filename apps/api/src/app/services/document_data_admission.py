"""Application boundary for document-derived data admission.

This service resolves the persisted DocumentParse closure for one Research Run
and then delegates the immutable payload to the pure document observation
pipeline. ``prepare`` owns authorization, exact parse selection and frozen
producer input identity; ``execute`` performs only deterministic extraction.
Artifact conversion, quality evaluation and publication remain downstream
authorities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.db.models import DocumentParseModel, ResearchInputBindingModel
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import DocumentSourcePolicy, ResearchContract
from app.schemas.crossmatch import CrossmatchResult
from app.schemas.data_artifacts import (
    DataSourceSnapshotProjection,
    DocumentObservationAdmissionCode,
    TypedDocumentObservation,
)
from app.schemas.document_observation_rules import DocumentObservationRuleSet
from app.schemas.manifest import CanonicalFieldId, ManifestBundle
from app.schemas.scientific_document import (
    DocumentParseCandidate,
    ScientificDataExtractionCandidate,
)
from app.services.document_parse_store import (
    DocumentParseNotFoundError,
    DocumentParseService,
    DocumentParseSourceSnapshot,
)
from services.data_pipeline.document_observation_rules import (
    load_document_observation_rule_set,
    verify_rule_set_pins,
)
from services.data_pipeline.document_observations import (
    DocumentObservationOutcome,
    PersistedDocumentContext,
    RawExtractionBatch,
    extract_document_observations,
)


class DocumentDataAdmissionError(RuntimeError):
    """Base error for deterministic document-data admission failures."""

    code = "DOCUMENT_DATA_ADMISSION_FAILED"


class DocumentParseSelectionAmbiguousError(DocumentDataAdmissionError):
    """Raised when one ResearchInput has more than one persisted parse."""

    code = "DOCUMENT_PARSE_SELECTION_AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class PreparedDocumentDataInput:
    """One fully resolved, persisted document input carried by a plan."""

    research_input_id: UUID
    document_parse_id: UUID
    candidate: DocumentParseCandidate
    context: PersistedDocumentContext
    snapshot: DocumentParseSourceSnapshot
    snapshot_projection: DataSourceSnapshotProjection


@dataclass(frozen=True, slots=True)
class DocumentDataAdmissionPlan:
    """Frozen application facts handed from ``prepare`` to ``execute``."""

    project_id: UUID
    run_id: UUID
    contract: ResearchContract
    crossmatch: CrossmatchResult
    manifests: ManifestBundle
    rules: DocumentObservationRuleSet
    prepared_inputs: tuple[PreparedDocumentDataInput, ...]
    policy: DocumentSourcePolicy
    case_capability: bool
    requested_fields: tuple[CanonicalFieldId, ...]
    producer_name: str
    producer_version: str
    producer_parameters: dict[str, Any]
    producer_input_facts: dict[str, Any]
    producer_input_hash: str


@dataclass(frozen=True, slots=True)
class DocumentDataAdmissionBatch:
    """Complete deterministic output for one prepared admission plan."""

    raw_candidates: tuple[ScientificDataExtractionCandidate, ...]
    accepted: tuple[TypedDocumentObservation, ...]
    outcomes: tuple[DocumentObservationOutcome, ...]
    producer_output_summary: dict[str, Any]
    outcome_counts: dict[str, int]
    producer_name: str
    producer_version: str
    producer_input_hash: str
    producer_output_hash: str
    rule_set_id: str
    rule_set_version: str
    configuration_hash: str


class DocumentDataAdmissionService:
    """Prepare and execute document observations inside cleaning_data."""

    def __init__(
        self,
        *,
        factory,
        document_parses: DocumentParseService,
        manifests: ManifestBundle,
    ) -> None:
        self._factory = factory
        self._document_parses = document_parses
        self._manifests = manifests
        self._rules = load_document_observation_rule_set()
        verify_rule_set_pins(self._rules, manifests=manifests)

    async def prepare(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        contract: ResearchContract,
        crossmatch: CrossmatchResult,
    ) -> DocumentDataAdmissionPlan | None:
        """Resolve and freeze the exact persisted inputs for one Run."""

        policy = contract.data_requirements.document_source_policy
        case_capability = "document_research_input" in (
            self._manifests.case_manifest.document_source_classes
        )
        bound_input_ids = self._bound_research_inputs(
            project_id=project_id,
            run_id=run_id,
            draft_id=UUID(str(contract.created_from_draft_id)),
        )
        if not bound_input_ids:
            return None
        parse_ids_by_input = self._parse_ids_for_inputs(
            project_id=project_id, research_input_ids=bound_input_ids
        )
        prepared_inputs: list[PreparedDocumentDataInput] = []
        for research_input_id in sorted(parse_ids_by_input):
            parse_ids = parse_ids_by_input[research_input_id]
            if not parse_ids:
                continue
            if len(parse_ids) != 1:
                raise DocumentParseSelectionAmbiguousError(
                    "one ResearchInput has multiple persisted DocumentParse records"
                )
            document_parse_id = parse_ids[0]
            candidate = await self._document_parses.get_candidate(
                project_id=project_id,
                document_parse_id=document_parse_id,
            )
            if candidate.research_input_id != str(research_input_id):
                raise DocumentParseNotFoundError(
                    "DocumentParse does not bind its ResearchInput"
                )
            snapshot = self._document_parses.source_snapshot(
                project_id=project_id,
                document_parse_id=document_parse_id,
            )
            context = PersistedDocumentContext(
                research_input_id=str(research_input_id),
                document_parse_id=str(document_parse_id),
                source_snapshot_id=str(snapshot.id),
            )
            prepared_inputs.append(
                PreparedDocumentDataInput(
                    research_input_id=research_input_id,
                    document_parse_id=document_parse_id,
                    candidate=candidate,
                    context=context,
                    snapshot=snapshot,
                    snapshot_projection=self._snapshot_projection(context, snapshot),
                )
            )
        if not prepared_inputs:
            return None

        ordered_inputs = tuple(
            sorted(
                prepared_inputs,
                key=lambda item: (
                    str(item.research_input_id),
                    str(item.document_parse_id),
                ),
            )
        )
        producer_input_facts = self._producer_input_facts(
            contract=contract,
            policy=policy,
            crossmatch=crossmatch,
            inputs=ordered_inputs,
        )
        producer_parameters = {
            "rule_set_id": self._rules.rule_set_id,
            "rule_set_version": self._rules.version,
            "configuration_hash": self._rules.configuration_hash,
        }
        return DocumentDataAdmissionPlan(
            project_id=project_id,
            run_id=run_id,
            contract=contract,
            crossmatch=crossmatch,
            manifests=self._manifests,
            rules=self._rules,
            prepared_inputs=ordered_inputs,
            policy=policy,
            case_capability=case_capability,
            requested_fields=tuple(sorted(contract.requested_fields)),
            producer_name=self._rules.producer_name,
            producer_version=self._rules.producer_version,
            producer_parameters=producer_parameters,
            producer_input_facts=producer_input_facts,
            producer_input_hash=compute_canonical_payload_hash(producer_input_facts),
        )

    def execute(self, plan: DocumentDataAdmissionPlan) -> DocumentDataAdmissionBatch:
        """Execute only the pure extraction stage of a prepared plan."""

        raw_candidates: list[ScientificDataExtractionCandidate] = []
        accepted: list[TypedDocumentObservation] = []
        outcomes: list[DocumentObservationOutcome] = []
        outcome_counts: dict[str, int] = {}
        for item in plan.prepared_inputs:
            extracted: RawExtractionBatch = extract_document_observations(
                parse=item.candidate,
                context=item.context,
                snapshot_projection=item.snapshot_projection,
                contract_policy=plan.policy,
                case_capability=plan.case_capability,
                requested_fields=plan.requested_fields,
                manifests=plan.manifests,
                crossmatch=plan.crossmatch,
                rules=plan.rules,
            )
            raw_candidates.extend(extracted.raw_candidates)
            accepted.extend(extracted.accepted)
            outcomes.extend(extracted.outcomes)
            for outcome in extracted.outcomes:
                status = outcome.status.value
                outcome_counts[status] = outcome_counts.get(status, 0) + 1

        ordered_raw = tuple(sorted(raw_candidates, key=lambda item: item.candidate_id))
        ordered_accepted = tuple(sorted(accepted, key=lambda item: item.observation_id))
        ordered_outcomes = tuple(
            sorted(
                outcomes,
                key=lambda item: (
                    item.raw_candidate_id,
                    item.status.value,
                    item.code.value if item.code is not None else "",
                ),
            )
        )
        output_summary: dict[str, Any] = {
            "producer_name": plan.producer_name,
            "producer_version": plan.producer_version,
            "rule_set": {
                "id": plan.rules.rule_set_id,
                "version": plan.rules.version,
                "configuration_hash": plan.rules.configuration_hash,
            },
            "raw_candidate_count": len(ordered_raw),
            "accepted_count": len(ordered_accepted),
            "outcome_counts": dict(sorted(outcome_counts.items())),
            "raw_candidates": [
                item.model_dump(mode="json", exclude={"created_at"})
                for item in ordered_raw
            ],
            "accepted_observations": [
                item.model_dump(mode="json") for item in ordered_accepted
            ],
            "outcomes": [
                {
                    "raw_candidate_id": item.raw_candidate_id,
                    "status": item.status.value,
                    "code": item.code.value if item.code is not None else None,
                }
                for item in ordered_outcomes
            ],
            "unsupported_regions": [
                {
                    "raw_candidate_id": item.raw_candidate_id,
                    "status": item.status.value,
                    "code": item.code.value,
                }
                for item in ordered_outcomes
                if item.code is not None
                and item.code is DocumentObservationAdmissionCode.document_parse_unsupported
            ],
        }
        return DocumentDataAdmissionBatch(
            raw_candidates=ordered_raw,
            accepted=ordered_accepted,
            outcomes=ordered_outcomes,
            producer_output_summary=output_summary,
            outcome_counts=dict(sorted(outcome_counts.items())),
            producer_name=plan.producer_name,
            producer_version=plan.producer_version,
            producer_input_hash=plan.producer_input_hash,
            producer_output_hash=compute_canonical_payload_hash(output_summary),
            rule_set_id=plan.rules.rule_set_id,
            rule_set_version=plan.rules.version,
            configuration_hash=plan.rules.configuration_hash,
        )

    def _bound_research_inputs(
        self, *, project_id: UUID, run_id: UUID, draft_id: UUID
    ) -> tuple[UUID, ...]:
        """Resolve only this Run or its Contract draft within the Project."""

        with self._factory() as session:
            rows = tuple(
                session.scalars(
                    select(ResearchInputBindingModel.input_id)
                    .where(
                        ResearchInputBindingModel.project_id == project_id,
                        (
                            (ResearchInputBindingModel.contract_draft_id == draft_id)
                            | (ResearchInputBindingModel.run_id == run_id)
                        ),
                    )
                    .order_by(ResearchInputBindingModel.input_id)
                )
            )
        return tuple(dict.fromkeys(rows))

    def _parse_ids_for_inputs(
        self, *, project_id: UUID, research_input_ids: tuple[UUID, ...]
    ) -> dict[UUID, tuple[UUID, ...]]:
        grouped: dict[UUID, list[UUID]] = {}
        with self._factory() as session:
            rows = session.execute(
                select(
                    DocumentParseModel.research_input_id,
                    DocumentParseModel.id,
                )
                .where(
                    DocumentParseModel.project_id == project_id,
                    DocumentParseModel.research_input_id.in_(research_input_ids),
                )
                .order_by(
                    DocumentParseModel.research_input_id,
                    DocumentParseModel.id,
                )
            )
            for research_input_id, document_parse_id in rows:
                grouped.setdefault(research_input_id, []).append(document_parse_id)
        return {key: tuple(dict.fromkeys(values)) for key, values in grouped.items()}

    def _snapshot_projection(
        self, context: PersistedDocumentContext, snapshot: DocumentParseSourceSnapshot
    ) -> DataSourceSnapshotProjection:
        """Project every persisted SourceSnapshot fact without synthesis."""

        return DataSourceSnapshotProjection(
            snapshot_id=f"research-input.{context.research_input_id}",
            source_id=snapshot.source_id,
            source_type=snapshot.source_type,
            retrieved_at=snapshot.retrieved_at,
            query=snapshot.query,
            query_hash=snapshot.query_hash,
            source_version_or_etag=snapshot.source_version_or_etag,
            content_hash=snapshot.content_hash,
            license_note=snapshot.license_note,
            cache_version=snapshot.cache_version,
            request_metadata=dict(snapshot.request_metadata),
        )

    def _producer_input_facts(
        self,
        *,
        contract: ResearchContract,
        policy: DocumentSourcePolicy,
        crossmatch: CrossmatchResult,
        inputs: tuple[PreparedDocumentDataInput, ...],
    ) -> dict[str, Any]:
        """Build the single canonical payload committed by the producer hash."""

        return {
            "contract": {
                "id": contract.id,
                "version": contract.version,
                "content_hash": contract.content_hash,
                "document_source_policy": policy.value,
                "requested_fields": sorted(contract.requested_fields),
            },
            "manifest_pins": {
                "case": {
                    "id": self._manifests.case_manifest.case_id,
                    "version": self._manifests.case_manifest.manifest_version,
                    "content_hash": self._manifests.case_manifest.content_hash,
                },
                "field": {
                    "id": self._manifests.field_manifest.manifest_id,
                    "version": self._manifests.field_manifest.manifest_version,
                    "content_hash": self._manifests.field_manifest.content_hash,
                },
            },
            "crossmatch": {
                "result_id": crossmatch.result_id,
                "input_hash": crossmatch.input_hash,
                "output_hash": crossmatch.output_hash,
                "content_hash": crossmatch.content_hash,
            },
            "rule_set": {
                "id": self._rules.rule_set_id,
                "version": self._rules.version,
                "configuration_hash": self._rules.configuration_hash,
            },
            "document_inputs": [
                {
                    "research_input_id": str(item.research_input_id),
                    "document_parse_id": str(item.document_parse_id),
                    "candidate_parse_id": item.candidate.parse_id,
                    "canonical_output_hash": item.candidate.canonical_output_hash,
                    "persisted_source_snapshot_id": str(item.snapshot.id),
                    "snapshot_projection": item.snapshot_projection.model_dump(
                        mode="json"
                    ),
                }
                for item in inputs
            ],
        }


__all__ = [
    "DocumentDataAdmissionBatch",
    "DocumentDataAdmissionError",
    "DocumentDataAdmissionPlan",
    "DocumentDataAdmissionService",
    "DocumentParseSelectionAmbiguousError",
    "PreparedDocumentDataInput",
]
