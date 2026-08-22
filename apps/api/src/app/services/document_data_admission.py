"""Application boundary for document-derived data admission.

This service owns persistence/application facts only: Project ownership,
ResearchInput bindings, persisted DocumentParse lookup, persisted
SourceSnapshot lookup, canonical parse retrieval, locator-free integrity
delegation to ``DocumentParseService``, and invocation of the pure
pipeline. Numeric conversion, field mapping algorithms, and Dataset assembly
live in their own authorities and never here.
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
    TypedDocumentObservation,
)
from app.schemas.manifest import ManifestBundle
from app.services.document_parse_store import (
    DocumentParseNotFoundError,
    DocumentParseService,
)
from services.data_pipeline.data_artifacts.policy import load_unit_conversion_catalog
from services.data_pipeline.document_observation_rules import (
    load_document_observation_rule_set,
    verify_rule_set_pins,
)
from services.data_pipeline.document_observations import (
    PersistedDocumentContext,
    RawExtractionBatch,
    extract_document_observations,
)


@dataclass(frozen=True, slots=True)
class DocumentDataAdmissionBatch:
    """Typed admitted batch plus the pipeline→persisted snapshot bindings."""

    accepted: tuple[TypedDocumentObservation, ...]
    snapshot_bindings: dict[str, str]
    producer_input_facts: tuple[dict[str, Any], ...]
    producer_output_summaries: tuple[dict[str, Any], ...]
    outcome_counts: dict[str, int]
    rule_set_id: str
    rule_set_version: str
    configuration_hash: str

    @property
    def producer_input_hash(self) -> str:
        return compute_canonical_payload_hash(list(self.producer_input_facts))

    @property
    def producer_output_hash(self) -> str:
        return compute_canonical_payload_hash(list(self.producer_output_summaries))


class DocumentDataAdmissionService:
    """Build the admitted document observation batch for one cleaning step."""

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

    async def build(
        self,
        *,
        project_id: UUID,
        contract: ResearchContract,
        crossmatch: CrossmatchResult,
    ) -> DocumentDataAdmissionBatch:
        policy = contract.data_requirements.document_source_policy
        capability = "document_research_input" in (
            self._manifests.case_manifest.document_source_classes
        )
        bound_input_ids = self._bound_research_inputs(
            project_id=project_id,
            draft_id=UUID(str(contract.created_from_draft_id)),
        )
        if not bound_input_ids:
            return self._empty_batch()
        parse_ids_by_input = self._parse_ids_for_inputs(
            project_id=project_id, research_input_ids=bound_input_ids
        )
        accepted: list[TypedDocumentObservation] = []
        input_facts: list[dict[str, Any]] = []
        output_summaries: list[dict[str, Any]] = []
        snapshot_bindings: dict[str, str] = {}
        outcome_counts: dict[str, int] = {}
        for research_input_id in sorted(parse_ids_by_input):
            for document_parse_id in sorted(parse_ids_by_input[research_input_id]):
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
                projection = self._snapshot_projection(context, snapshot)
                pipeline_snapshot_id = projection.snapshot_id
                existing = snapshot_bindings.setdefault(
                    pipeline_snapshot_id, str(snapshot.id)
                )
                if existing != str(snapshot.id):
                    raise ValueError(
                        "one pipeline document snapshot must bind exactly one "
                        "persisted SourceSnapshot"
                    )
                batch: RawExtractionBatch = extract_document_observations(
                    parse=candidate,
                    context=context,
                    snapshot_projection=projection,
                    contract_policy=policy,
                    case_capability=capability,
                    requested_fields=tuple(contract.requested_fields),
                    manifests=self._manifests,
                    crossmatch=crossmatch,
                    rules=self._rules,
                    conversion_catalog=load_unit_conversion_catalog(),
                )
                accepted.extend(batch.accepted)
                input_facts.append(batch.producer_input_facts)
                output_summaries.append(batch.producer_output_summary)
                for outcome in batch.outcomes:
                    key = outcome.status.value
                    outcome_counts[key] = outcome_counts.get(key, 0) + 1
        return DocumentDataAdmissionBatch(
            accepted=tuple(accepted),
            snapshot_bindings=snapshot_bindings,
            producer_input_facts=tuple(input_facts),
            producer_output_summaries=tuple(output_summaries),
            outcome_counts=outcome_counts,
            rule_set_id=self._rules.rule_set_id,
            rule_set_version=self._rules.version,
            configuration_hash=self._rules.configuration_hash,
        )

    def _bound_research_inputs(
        self, *, project_id: UUID, draft_id: UUID
    ) -> tuple[UUID, ...]:
        """Resolve run-bound inputs first, then the confirmed Contract's draft."""

        with self._factory() as session:
            rows = tuple(
                session.scalars(
                    select(ResearchInputBindingModel.input_id).where(
                        ResearchInputBindingModel.project_id == project_id,
                        (
                            (ResearchInputBindingModel.contract_draft_id == draft_id)
                            | (ResearchInputBindingModel.run_id.is_not(None))
                        ),
                    )
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
                ).where(
                    DocumentParseModel.project_id == project_id,
                    DocumentParseModel.research_input_id.in_(research_input_ids),
                )
            )
            for research_input_id, document_parse_id in rows:
                grouped.setdefault(research_input_id, []).append(document_parse_id)
        return {
            key: tuple(dict.fromkeys(values)) for key, values in grouped.items()
        }

    def _snapshot_projection(self, context, snapshot) -> DataSourceSnapshotProjection:
        """Logical data-pipeline projection mirroring the persisted row."""

        return DataSourceSnapshotProjection(
            snapshot_id=f"research-input.{context.research_input_id}",
            source_id=snapshot.source_id,
            source_type=snapshot.source_type,
            retrieved_at=snapshot.retrieved_at,
            query=snapshot.query,
            query_hash=snapshot.query_hash,
            source_version_or_etag=None,
            content_hash=snapshot.content_hash,
            license_note=snapshot.license_note,
            cache_version=snapshot.cache_version,
            request_metadata={},
        )

    def _empty_batch(self) -> DocumentDataAdmissionBatch:
        return DocumentDataAdmissionBatch(
            accepted=(),
            snapshot_bindings={},
            producer_input_facts=(),
            producer_output_summaries=(),
            outcome_counts={},
            rule_set_id=self._rules.rule_set_id,
            rule_set_version=self._rules.version,
            configuration_hash=self._rules.configuration_hash,
        )


__all__ = [
    "DocumentDataAdmissionBatch",
    "DocumentDataAdmissionService",
]
