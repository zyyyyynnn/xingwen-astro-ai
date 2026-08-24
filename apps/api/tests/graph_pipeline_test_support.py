"""Deterministic, fully published inputs for focused Evidence Graph pipeline tests.

The LiteratureRelations payload is produced by the real LiteratureRelation Pipeline admission
pipeline.  The frozen Paper Acquisition Benchmark fixture predates UUID database identifiers, so the
upstream LiteratureClaim Pipeline candidates are first rebound to deterministic UUID version IDs
and then LiteratureRelation Pipeline is rerun.  No unvalidated candidate dictionaries cross the Evidence Graph
read port.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import json
from types import SimpleNamespace
from uuid import UUID, uuid5

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.artifact_publication import canonical_artifact_content_payload
from app.schemas.core import (
    EvidenceDetail,
    ProducerExecutionDetail,
    ProducerReference,
    SourceMode,
    SourceSnapshotDetail,
)
from app.schemas.data_artifacts import (
    DatasetArtifactCandidate,
    FieldDictionaryArtifactCandidate,
)
from app.schemas.data_quality import DataQualityProjection
from app.schemas.enums import GraphEdgeType
from app.schemas.graph_artifact import (
    GraphBuildRequest,
    GraphBuildScope,
    GraphIntegrityStage,
    GraphLayoutHint,
    GraphPolicySet,
    GraphProgressiveInput,
    GraphRejectionReason,
    GraphStructuralEdgeRequest,
)
from app.schemas.literature_claim import (
    LiteratureClaimsCandidate,
    compute_literature_claims_output_hash,
)
from app.schemas.literature_relation import LiteratureRelationStatus
from app.workflow.publisher import admit_artifact_candidate

from services.data_pipeline.data_artifacts.admission import (
    validate_data_artifact_domain,
    validate_data_artifact_evidence,
)
from services.data_pipeline.data_quality import (
    admit_data_artifact_quality,
    build_data_quality_publication_validator,
    evaluate_data_quality,
)
from services.graph_pipeline.pipeline import build_complete_progressive_input
from services.graph_pipeline.ports import (
    GraphDataVersionSelection,
    GraphInputIntegrityError,
    GraphInputVersionSelection,
    PersistedEvidenceBinding,
    PersistedSourceSnapshotBinding,
    PublishedArtifactVersionPins,
    PublishedDataGraphInputs,
    PublishedDatasetVersion,
    PublishedFieldDictionaryVersion,
    PublishedGraphInputs,
    PublishedLiteratureRelationsVersion,
)
from services.paper_pipeline.benchmark import load_frozen_benchmark
from services.paper_pipeline.relation import LiteratureClaimsArtifactVersionInput
from services.paper_pipeline.relation_benchmark_cases import (
    _PROJECT_ID,
    _REPLAY_MODEL_NAME,
    _REPLAY_PARAMETERS,
    _admit,
    _claim_inputs,
    _relation_fixture,
)


NOW = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
UUID_NAMESPACE = UUID("6ca86f2b-72c6-5f0f-b1f4-04ac4fb67334")
ZERO_HASH = "sha256:" + "0" * 64


def stable_uuid(label: str) -> str:
    """Return a stable UUID string for one fixture-owned storage identity."""

    return str(uuid5(UUID_NAMESPACE, label))


class ExactPublishedGraphInputReader:
    """In-memory exact-version read port; it never implements latest/page reads."""

    def __init__(self, inputs: PublishedGraphInputs) -> None:
        self.inputs = inputs
        self.selections: list[GraphInputVersionSelection] = []

    def read(self, selection: GraphInputVersionSelection) -> PublishedGraphInputs:
        if type(selection) is not GraphInputVersionSelection:
            raise GraphInputIntegrityError(
                "reader requires exact typed selection",
                stage=GraphIntegrityStage.input_schema,
                reason=GraphRejectionReason.schema_invalid,
                path="input_versions",
            )
        self.selections.append(selection)
        if selection != self.inputs.selection:
            raise GraphInputIntegrityError(
                "selected ArtifactVersion is unknown",
                stage=GraphIntegrityStage.artifact_version,
                reason=GraphRejectionReason.input_version_unknown,
                path="input_versions",
            )
        return self.inputs


@dataclass(frozen=True, slots=True)
class LiteratureGraphFixture:
    """Reusable production-pipeline fixture for one real LiteratureRelation Pipeline relation pair."""

    inputs: PublishedGraphInputs
    reader: ExactPublishedGraphInputReader
    scope: GraphBuildScope
    relation_id: str
    source_claim_id: str
    target_claim_id: str
    source_paper_id: str
    target_paper_id: str

    def request(
        self,
        *,
        policies: GraphPolicySet | None = None,
        layout_hint: GraphLayoutHint | None = None,
        progressive: GraphProgressiveInput | None = None,
        chunk_size: int = 10_000,
        reverse_chunks: bool = False,
        scope: GraphBuildScope | None = None,
    ) -> GraphBuildRequest:
        selected_scope = self.scope if scope is None else scope
        relation_version_id = (
            self.inputs.selection.literature_relations_artifact_version_id
        )
        data_selection = self.inputs.selection.data
        dataset_version_id = (
            data_selection.dataset_artifact_version_id
            if data_selection is not None
            else None
        )
        dictionary_version_id = (
            data_selection.field_dictionary_artifact_version_id
            if data_selection is not None
            else None
        )
        if progressive is None:
            progressive = build_complete_progressive_input(
                progressive_id="progressive.evidence_graph.real_literature_relation",
                literature_relations_artifact_version_id=relation_version_id,
                dataset_artifact_version_id=dataset_version_id,
                field_dictionary_artifact_version_id=dictionary_version_id,
                scope=selected_scope,
                chunk_size=chunk_size,
                reverse_chunks=reverse_chunks,
            )
        return GraphBuildRequest(
            project_id=self.inputs.selection.project_id,
            literature_relations_artifact_version_id=relation_version_id,
            dataset_artifact_version_id=dataset_version_id,
            field_dictionary_artifact_version_id=dictionary_version_id,
            scope=selected_scope,
            policies=GraphPolicySet() if policies is None else policies,
            progressive=progressive,
            layout_hint=GraphLayoutHint() if layout_hint is None else layout_hint,
        )


def build_literature_graph_fixture(
    *,
    relation_status: LiteratureRelationStatus = LiteratureRelationStatus.accepted,
    reverse_published_bindings: bool = False,
    include_shared_candidate_relation: bool = False,
) -> LiteratureGraphFixture:
    """Build a real LiteratureRelation Pipeline literature-only envelope for one frozen Paper Acquisition Benchmark pair.

    ``accepted`` is the happy-path pair. ``candidate`` is retained by LiteratureRelation Pipeline but
    must be rejected by Evidence Graph's accepted-relation scope.
    """

    if relation_status not in {
        LiteratureRelationStatus.accepted,
        LiteratureRelationStatus.candidate,
    }:
        raise ValueError(
            "fixture requires a LiteratureRelation Pipeline publishable relation status"
        )

    benchmark = load_frozen_benchmark()
    claim_inputs = _uuid_ready_claim_inputs(benchmark)
    benchmark_relation = next(
        item
        for item in benchmark.relations
        if item.status.value == relation_status.value
    )
    benchmark_trace = next(
        item
        for item in benchmark.reasoning_traces
        if item.trace_id == benchmark_relation.reasoning_trace_id
    )
    literature_relation_fixture = _relation_fixture(
        benchmark=benchmark,
        relation=benchmark_relation,
        trace=benchmark_trace,
        claims=claim_inputs,
    )
    if include_shared_candidate_relation:
        if relation_status is not LiteratureRelationStatus.accepted:
            raise ValueError(
                "shared-Evidence fixture requires the accepted Relation scope"
            )
        shared_relation = next(
            item
            for item in benchmark.relations
            if item.status.value == LiteratureRelationStatus.candidate.value
            and set(item.evidence_ids) & set(benchmark_relation.evidence_ids)
        )
        shared_trace = next(
            item
            for item in benchmark.reasoning_traces
            if item.trace_id == shared_relation.reasoning_trace_id
        )
        shared_fixture = _relation_fixture(
            benchmark=benchmark,
            relation=shared_relation,
            trace=shared_trace,
            claims=claim_inputs,
        )
        versions = {**literature_relation_fixture.versions, **shared_fixture.versions}
        admission = literature_relation_fixture.pipeline.admit(
            literature_claim_artifact_version_ids=tuple(sorted(versions)),
            literature_claim_versions=versions,
            project_id=_PROJECT_ID,
            model_response=json.dumps(
                {
                    "schema_version": "1.0.0",
                    "relations": [
                        literature_relation_fixture.payload,
                        shared_fixture.payload,
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
            model_name=_REPLAY_MODEL_NAME,
            parameters=_REPLAY_PARAMETERS,
            confidence_assessments={
                literature_relation_fixture.confidence.assessment_id: literature_relation_fixture.confidence,
                shared_fixture.confidence.assessment_id: shared_fixture.confidence,
            },
        )
    else:
        admission = _admit(fixture=literature_relation_fixture)
    candidate = admission.publisher_candidate
    if candidate is None:
        raise AssertionError(
            "selected real LiteratureRelation Pipeline case did not publish a candidate"
        )
    selected = tuple(
        item for item in candidate.relations if item.status is relation_status
    )
    if len(selected) != 1:
        raise AssertionError(
            "real LiteratureRelation Pipeline fixture relation status drifted"
        )
    relation = selected[0]

    relation_version_id = stable_uuid(
        f"artifact-version:literature-relations:{relation_status.value}"
    )
    project_id = stable_uuid("project:evidence_graph-real-literature_relation")
    published = _published_literature_version(
        candidate=candidate,
        project_id=project_id,
        relation_version_id=relation_version_id,
        reverse_bindings=reverse_published_bindings,
    )
    selection = GraphInputVersionSelection(
        project_id=project_id,
        literature_relations_artifact_version_id=relation_version_id,
    )
    inputs = PublishedGraphInputs(
        selection=selection,
        literature_relations=published,
    )

    claims = {item.claim_id: item for item in candidate.claims}
    source_claim = claims[relation.source_claim_id]
    target_claim = claims[relation.target_claim_id]
    structural = GraphStructuralEdgeRequest(
        edge_type=GraphEdgeType.supports_finding,
        source_paper_id=source_claim.paper_id,
        target_claim_id=source_claim.claim_id,
    )
    scope = GraphBuildScope(
        literature_paper_ids=tuple(
            sorted({source_claim.paper_id, target_claim.paper_id})
        ),
        literature_claim_ids=tuple(
            sorted({source_claim.claim_id, target_claim.claim_id})
        ),
        accepted_relation_ids=(relation.relation_id,),
        structural_edges=(structural,),
    )
    reader = ExactPublishedGraphInputReader(inputs)
    return LiteratureGraphFixture(
        inputs=inputs,
        reader=reader,
        scope=scope,
        relation_id=relation.relation_id,
        source_claim_id=source_claim.claim_id,
        target_claim_id=target_claim.claim_id,
        source_paper_id=source_claim.paper_id,
        target_paper_id=target_claim.paper_id,
    )


def build_data_graph_fixture(
    *,
    reverse_published_bindings: bool = False,
    reverse_data_bindings: bool = False,
) -> LiteratureGraphFixture:
    """Build a typed Evidence Graph input from real Data Artifact and passing Data Quality Evaluation outputs.

    The identifier-conflict fixture is intentionally used because its two
    canonical fields jointly retain mapped, selected, unselected,
    declared-null, unresolved, conflict, TransformationEvidence, and
    CrossmatchEvidence states.  Only storage UUID bindings are fixture-owned.
    """

    from test_data_quality_pipeline import make_quality_input

    literature = build_literature_graph_fixture(
        reverse_published_bindings=reverse_published_bindings
    )
    quality_input, build_result = make_quality_input(
        "star.tic_id",
        "star.name",
        scenario_id="identifier_conflict",
    )
    quality_result = evaluate_data_quality(quality_input)
    admitted = admit_data_artifact_quality(
        build_result=build_result,
        evaluation_input=quality_input,
        evaluation_result=quality_result,
    )

    project_id = literature.inputs.selection.project_id
    dataset_version_id = stable_uuid("artifact-version:evidence_graph-data:dataset")
    dictionary_version_id = stable_uuid(
        "artifact-version:evidence_graph-data:field-dictionary"
    )
    snapshots = _data_source_snapshot_bindings(build_result.dataset)
    dataset_evidence = _data_evidence_bindings(
        candidate=build_result.dataset,
        artifact_version_id=dataset_version_id,
        candidate_kind="dataset",
        crossmatch_evidence=quality_input.data_artifact_input.crossmatch_result.evidence,
        source_snapshot_bindings=snapshots,
        reverse=reverse_data_bindings,
    )
    dictionary_evidence = _data_evidence_bindings(
        candidate=build_result.dataset,
        artifact_version_id=dictionary_version_id,
        candidate_kind="field_dictionary",
        crossmatch_evidence=quality_input.data_artifact_input.crossmatch_result.evidence,
        source_snapshot_bindings=snapshots,
        reverse=reverse_data_bindings,
    )
    dataset_projection = _quality_projection(
        admitted=admitted,
        candidate=build_result.dataset,
        candidate_kind="dataset",
    )
    dictionary_projection = _quality_projection(
        admitted=admitted,
        candidate=build_result.field_dictionary,
        candidate_kind="field_dictionary",
    )
    snapshot_values = tuple(reversed(snapshots)) if reverse_data_bindings else snapshots
    dataset = PublishedDatasetVersion(
        pins=_published_data_pins(
            candidate=build_result.dataset,
            artifact_id=stable_uuid("artifact:evidence_graph-data:dataset"),
            artifact_version_id=dataset_version_id,
            project_id=project_id,
        ),
        candidate=build_result.dataset,
        quality_projection=dataset_projection,
        source_snapshot_bindings=snapshot_values,
        evidence_bindings=dataset_evidence,
    )
    dictionary = PublishedFieldDictionaryVersion(
        pins=_published_data_pins(
            candidate=build_result.field_dictionary,
            artifact_id=stable_uuid("artifact:evidence_graph-data:field-dictionary"),
            artifact_version_id=dictionary_version_id,
            project_id=project_id,
        ),
        candidate=build_result.field_dictionary,
        quality_projection=dictionary_projection,
        source_snapshot_bindings=snapshot_values,
        evidence_bindings=dictionary_evidence,
    )
    data_selection = GraphDataVersionSelection(
        dataset_artifact_version_id=dataset_version_id,
        field_dictionary_artifact_version_id=dictionary_version_id,
    )
    selection = GraphInputVersionSelection(
        project_id=project_id,
        literature_relations_artifact_version_id=(
            literature.inputs.selection.literature_relations_artifact_version_id
        ),
        data=data_selection,
    )
    inputs = PublishedGraphInputs(
        selection=selection,
        literature_relations=literature.inputs.literature_relations,
        data=PublishedDataGraphInputs(
            dataset=dataset,
            field_dictionary=dictionary,
        ),
    )
    scope = literature.scope.model_copy(update={"include_data": True})
    reader = ExactPublishedGraphInputReader(inputs)
    return replace(literature, inputs=inputs, reader=reader, scope=scope)


def _quality_projection(
    *,
    admitted: object,
    candidate: DatasetArtifactCandidate | FieldDictionaryArtifactCandidate,
    candidate_kind: str,
) -> DataQualityProjection:
    validator = build_data_quality_publication_validator(
        admitted,
        candidate_kind=candidate_kind,
    )
    if isinstance(candidate, FieldDictionaryArtifactCandidate):
        validator(
            SimpleNamespace(
                candidate=candidate,
                source_snapshot_ids=candidate.source_snapshot_ids,
                evidence_ids=candidate.evidence_ids,
            )
        )
        attestation = validator._data_quality_attestation
        return DataQualityProjection.model_validate_json(attestation.projection_json)

    from data_artifact_test_support import build_data_publication_bindings

    snapshots, evidence = build_data_publication_bindings(candidate)
    admitted_candidate = admit_artifact_candidate(
        candidate,
        schema_version=candidate.schema_version,
        source_snapshot_ids=candidate.source_snapshot_ids,
        evidence_ids=candidate.evidence_ids,
        evidence_validator=validate_data_artifact_evidence,
        domain_validator=validate_data_artifact_domain,
        quality_validator=validator,
        source_snapshot_bindings=snapshots,
        evidence_bindings=evidence,
    )
    projection = admitted_candidate.quality_projection
    if projection is None:
        raise AssertionError(
            "passing Data Quality Evaluation admission did not expose its projection"
        )
    return projection


def _published_data_pins(
    *,
    candidate: DatasetArtifactCandidate | FieldDictionaryArtifactCandidate,
    artifact_id: str,
    artifact_version_id: str,
    project_id: str,
) -> PublishedArtifactVersionPins:
    content_hash = compute_canonical_payload_hash(
        canonical_artifact_content_payload(candidate)
    )
    parameters_hash = compute_canonical_payload_hash(
        {
            "mapping_rule_set_content_hash": candidate.mapping_rule_set_content_hash,
            "conversion_catalog_content_hash": candidate.conversion_catalog_content_hash,
        }
    )
    producer = ProducerReference(
        type=candidate.producer.producer_type,
        name=candidate.producer.producer_name,
        version=candidate.producer.producer_version,
        parameters_hash=parameters_hash,
    )
    execution = ProducerExecutionDetail(
        id=stable_uuid(f"producer-execution:{artifact_version_id}"),
        run_id=stable_uuid(f"run:{artifact_version_id}"),
        step_key="build_data_artifacts",
        step_attempt_id=stable_uuid(f"step-attempt:{artifact_version_id}"),
        producer=producer,
        parameters={},
        parameters_hash=parameters_hash,
        input_hash=candidate.input_hash,
        output_hash=content_hash,
        status="completed",
        started_at=NOW,
        finished_at=NOW,
        latency_ms=1,
    )
    return PublishedArtifactVersionPins(
        artifact_id=artifact_id,
        artifact_version_id=artifact_version_id,
        project_id=project_id,
        version_number=1,
        schema_version=candidate.schema_version,
        content_hash=content_hash,
        input_hash=candidate.input_hash,
        output_hash=candidate.output_hash,
        source_mode=SourceMode.fixture,
        producer_execution=execution,
    )


def _data_source_snapshot_bindings(
    candidate: DatasetArtifactCandidate,
) -> tuple[PersistedSourceSnapshotBinding, ...]:
    values_by_snapshot = {
        value.provenance.pipeline_source_snapshot_id: value
        for value in candidate.source_values
    }
    bindings = []
    for pipeline_snapshot_id in candidate.source_snapshot_ids:
        source_value = values_by_snapshot[pipeline_snapshot_id]
        bindings.append(
            PersistedSourceSnapshotBinding(
                pipeline_source_snapshot_id=pipeline_snapshot_id,
                source_snapshot=SourceSnapshotDetail(
                    id=stable_uuid(f"source-snapshot:data:{pipeline_snapshot_id}"),
                    source_id=source_value.provenance.source_id,
                    source_type="database",
                    retrieved_at=NOW,
                    query={"fixture": pipeline_snapshot_id},
                    query_hash=source_value.provenance.query_hash,
                    source_version_or_etag="fixture-etag",
                    content_hash=source_value.provenance.pipeline_source_snapshot_content_hash,
                    license_note="Frozen Data Artifact/Data Quality Evaluation fixture provenance",
                    request_metadata={"data_level": "fixture"},
                ),
            )
        )
    return tuple(bindings)


def _data_evidence_bindings(
    *,
    candidate: DatasetArtifactCandidate,
    artifact_version_id: str,
    candidate_kind: str,
    crossmatch_evidence: tuple[object, ...],
    source_snapshot_bindings: tuple[PersistedSourceSnapshotBinding, ...],
    reverse: bool,
) -> tuple[PersistedEvidenceBinding, ...]:
    transformations = {
        item.evidence_id: item for item in candidate.transformation_evidence
    }
    crossmatch = {item.evidence_id: item for item in crossmatch_evidence}
    snapshot_ids = {
        item.pipeline_source_snapshot_id: item.persisted_source_snapshot_id
        for item in source_snapshot_bindings
    }
    bindings = []
    for evidence_id in candidate.evidence_ids:
        if evidence_id in transformations:
            transformation = transformations[evidence_id]
            pipeline_content_hash = transformation.content_hash
            pipeline_snapshot_id = transformation.provenance.pipeline_source_snapshot_id
            locator = transformation.provenance.model_dump(mode="json")
            target_type = "canonical_field"
            target_id = transformation.canonical_field_id
        else:
            item = crossmatch[evidence_id]
            pipeline_content_hash = item.content_hash
            locators = tuple((*item.left_locators, *item.right_locators))
            pipeline_snapshot_id = min(
                locator.source_snapshot_id for locator in locators
            )
            locator = {
                "crossmatch_evidence_id": evidence_id,
                "crossmatch_content_hash": item.content_hash,
            }
            target_type = "crossmatch"
            target_id = item.evidence_id
        persisted_id = stable_uuid(f"evidence:{candidate_kind}:{evidence_id}")
        bindings.append(
            PersistedEvidenceBinding(
                pipeline_evidence_id=evidence_id,
                pipeline_evidence_content_hash=pipeline_content_hash,
                pipeline_source_snapshot_id=pipeline_snapshot_id,
                pipeline_target_type=target_type,
                pipeline_target_id=target_id,
                pipeline_locator=locator,
                evidence=EvidenceDetail(
                    id=persisted_id,
                    artifact_version_id=artifact_version_id,
                    target_type=target_type,
                    target_id=target_id,
                    evidence_type="database_query",
                    source_snapshot_id=snapshot_ids[pipeline_snapshot_id],
                    locator=locator,
                    quote_or_value=None,
                    extraction_method="data_artifact_projection",
                    confidence=1.0,
                    created_at=NOW,
                ),
                is_restricted=False,
            )
        )
    values = tuple(bindings)
    return tuple(reversed(values)) if reverse else values


def _uuid_ready_claim_inputs(benchmark: object) -> dict[str, object]:
    """Rebind frozen LiteratureClaim Pipeline inputs to persistent UUIDs and revalidate hashes."""

    result: dict[str, object] = {}
    for benchmark_claim_id, item in _claim_inputs(benchmark).items():
        claim_version_id = stable_uuid(
            f"artifact-version:literature-claims:{benchmark_claim_id}"
        )
        content_payload = item.version.content.model_dump(
            mode="json", exclude_none=True
        )
        old_summary_version_id = content_payload["input_versions"][
            "paper_summary_artifact_version_id"
        ]
        summary_version_id = stable_uuid(
            f"artifact-version:paper-summary:{old_summary_version_id}"
        )
        content_payload["input_versions"]["paper_summary_artifact_version_id"] = (
            summary_version_id
        )
        content_payload["producer"]["input_versions"][
            "paper_summary_artifact_version_id"
        ] = summary_version_id
        for claim in content_payload["claims"]:
            claim["source_paper_summary_artifact_version_id"] = summary_version_id
        content_payload["output_hash"] = ZERO_HASH
        content_payload["producer"]["output_hash"] = ZERO_HASH
        output_hash = compute_literature_claims_output_hash(content_payload)
        content_payload["output_hash"] = output_hash
        content_payload["producer"]["output_hash"] = output_hash
        content = LiteratureClaimsCandidate.model_validate(content_payload)
        version = LiteratureClaimsArtifactVersionInput(
            artifact_version_id=claim_version_id,
            schema_version=content.schema_version,
            content_hash=compute_canonical_payload_hash(
                canonical_artifact_content_payload(content)
            ),
            project_id=item.version.project_id,
            content=content,
        )
        result[benchmark_claim_id] = replace(
            item,
            artifact_version_id=claim_version_id,
            version=version,
        )
    return result


def _published_literature_version(
    *,
    candidate: object,
    project_id: str,
    relation_version_id: str,
    reverse_bindings: bool,
) -> PublishedLiteratureRelationsVersion:
    candidate_payload = canonical_artifact_content_payload(candidate)
    content_hash = compute_canonical_payload_hash(candidate_payload)
    nested_producer = candidate.producer
    producer = ProducerReference(
        type=nested_producer.producer_type,
        name=nested_producer.producer_name,
        version=nested_producer.producer_version,
        model_name=nested_producer.model_name,
        prompt_name=nested_producer.prompt_name,
        prompt_version=nested_producer.prompt_version,
        prompt_hash=nested_producer.prompt_hash,
        parameters_hash=nested_producer.parameters_hash,
    )
    execution = ProducerExecutionDetail(
        id=stable_uuid(f"producer-execution:{relation_version_id}"),
        run_id=stable_uuid(f"run:{relation_version_id}"),
        step_key=nested_producer.step_key,
        step_attempt_id=stable_uuid(f"step-attempt:{relation_version_id}"),
        producer=producer,
        parameters={},
        parameters_hash=nested_producer.parameters_hash,
        input_hash=candidate.input_hash,
        output_hash=content_hash,
        status="completed",
        started_at=NOW,
        finished_at=NOW,
        latency_ms=1,
    )
    pins = PublishedArtifactVersionPins(
        artifact_id=stable_uuid(
            f"artifact:literature-relations:{candidate.relations[0].status.value}"
        ),
        artifact_version_id=relation_version_id,
        project_id=project_id,
        version_number=1,
        schema_version=candidate.schema_version,
        content_hash=content_hash,
        input_hash=candidate.input_hash,
        output_hash=candidate.output_hash,
        source_mode=SourceMode.fixture,
        producer_execution=execution,
    )

    pipeline_evidence = {item.evidence_id: item for item in candidate.evidence}
    snapshot_bindings = []
    for pipeline_snapshot_id in candidate.source_snapshot_ids:
        evidence = next(
            item
            for item in candidate.evidence
            if item.source_snapshot_id == pipeline_snapshot_id
        )
        snapshot_bindings.append(
            PersistedSourceSnapshotBinding(
                pipeline_source_snapshot_id=pipeline_snapshot_id,
                source_snapshot=SourceSnapshotDetail(
                    id=stable_uuid(f"source-snapshot:{pipeline_snapshot_id}"),
                    source_id=evidence.source_id,
                    source_type="benchmark",
                    retrieved_at=NOW,
                    query={"fixture": pipeline_snapshot_id},
                    query_hash=compute_canonical_payload_hash(
                        {"fixture": pipeline_snapshot_id}
                    ),
                    source_version_or_etag=evidence.source_snapshot_version,
                    content_hash=evidence.source_snapshot_content_hash,
                    license_note="Frozen paper acquisition benchmark fixture",
                    request_metadata={"data_level": "benchmark"},
                ),
            )
        )
    snapshot_by_pipeline = {
        item.pipeline_source_snapshot_id: item for item in snapshot_bindings
    }
    evidence_bindings = []
    for reference in candidate.evidence_references:
        evidence = pipeline_evidence[reference.evidence_id]
        persisted_snapshot = snapshot_by_pipeline[reference.source_snapshot_id]
        evidence_bindings.append(
            PersistedEvidenceBinding(
                pipeline_evidence_id=reference.evidence_id,
                pipeline_evidence_content_hash=compute_canonical_payload_hash(
                    evidence.model_dump(mode="json", exclude_none=True)
                ),
                pipeline_source_snapshot_id=reference.source_snapshot_id,
                pipeline_target_type="relation",
                pipeline_target_id=reference.relation_id,
                pipeline_locator={
                    "summary_evidence_id": reference.evidence_id,
                    "source_record_id": evidence.source_record_id,
                },
                evidence=EvidenceDetail(
                    id=stable_uuid(
                        "evidence:"
                        f"{relation_version_id}:{reference.relation_id}:"
                        f"{reference.evidence_id}"
                    ),
                    artifact_version_id=relation_version_id,
                    target_type="relation",
                    target_id=reference.relation_id,
                    evidence_type="paper_text",
                    source_snapshot_id=(
                        persisted_snapshot.persisted_source_snapshot_id
                    ),
                    paper_id=reference.paper_id,
                    locator={
                        "summary_evidence_id": reference.evidence_id,
                        "source_record_id": evidence.source_record_id,
                    },
                    quote_or_value="Frozen benchmark evidence",
                    extraction_method="literature_admission",
                    confidence=1.0,
                    created_at=NOW,
                ),
                is_restricted=False,
            )
        )
    source_values = tuple(snapshot_bindings)
    evidence_values = tuple(evidence_bindings)
    if reverse_bindings:
        source_values = tuple(reversed(source_values))
        evidence_values = tuple(reversed(evidence_values))
    return PublishedLiteratureRelationsVersion(
        pins=pins,
        candidate=candidate,
        source_snapshot_bindings=source_values,
        evidence_bindings=evidence_values,
    )


__all__ = [
    "ExactPublishedGraphInputReader",
    "LiteratureGraphFixture",
    "build_data_graph_fixture",
    "build_literature_graph_fixture",
    "stable_uuid",
]
