from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from app.schemas.core import ArtifactKind, EvidenceDetail
from app.schemas.literature_claim import (
    compute_literature_claim_fingerprint,
    compute_literature_claims_output_hash,
)
from app.schemas.paper_summary import compute_paper_summary_output_hash
from app.services.public_presentation import (
    PresentationIntegrityError,
    build_artifact_presentation,
)
from app.schemas.literature_relation import literature_relation_adjudicable
from data_artifact_test_support import build_input
from graph_read_test_support import build_graph_read_fixture
from literature_artifact_test_support import build_literature_fixture
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.paper_pipeline.benchmark import load_frozen_benchmark
from services.paper_pipeline.claim_benchmark_cases import (
    build_frozen_claim_benchmark_cases,
)
from services.paper_pipeline.relation_benchmark_cases import (
    build_frozen_relation_benchmark_cases,
)
from services.paper_pipeline.demo_fixture import build_demo_collection
from services.paper_pipeline.demo_summary_fixture import build_demo_summary_read


def _persisted_dataset_evidence(candidate: object) -> tuple[EvidenceDetail, ...]:
    return tuple(
        EvidenceDetail(
            id=f"persisted.{item.evidence_id}",
            artifact_version_id="version.dataset",
            target_type="canonical_field",
            target_id=item.canonical_field_id,
            evidence_type="data_transformation",
            source_snapshot_id=item.locator.source_snapshot_id,
            locator=item.locator.model_dump(mode="json"),
            quote_or_value=(
                item.canonical_value
                if item.canonical_value is not None
                else item.raw_value
            ),
            extraction_method="data_artifact_admission",
            confidence=1.0,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        for item in candidate.transformation_evidence
    )


def test_presentation_accepts_persisted_json_for_every_data_artifact_kind() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))

    for candidate in (
        result.dataset,
        result.field_dictionary,
        result.source_collection,
    ):
        persisted_evidence = (
            _persisted_dataset_evidence(candidate)
            if candidate.kind == "dataset"
            else ()
        )
        presentation = build_artifact_presentation(
            ArtifactKind(candidate.kind),
            candidate.model_dump(mode="json"),
            persisted_evidence,
        )

        assert presentation.kind.value == candidate.kind
        assert presentation.entries
        if candidate.kind == "dataset":
            table = presentation.tables[0]
            assert table.rows
            assert table.rows[0].identity == "TIC 101"
            assert table.rows[0].cells[0].value == "TIC 101"
            assert set(table.rows[0].cells[0].evidence_ids) <= {
                item.id for item in persisted_evidence
            }
        if candidate.kind == "source_collection":
            assert [entry.title for entry in presentation.entries] == [
                f"来源 {index + 1}" for index in range(len(presentation.entries))
            ]


def test_literature_presentation_uses_persisted_evidence_ids() -> None:
    fixture = build_literature_fixture()
    version = fixture.artifacts.versions[fixture.relation_version_id]

    presentation = build_artifact_presentation(
        ArtifactKind.literature_relations,
        version.content,
        version.evidence,
    )

    expected = {
        item.id
        for item in version.evidence
        if item.target_type == "relation"
        and item.target_id == fixture.accepted_relation_id
    }
    entry = next(
        item
        for item in presentation.entries
        if item.key == fixture.accepted_relation_id
    )
    assert set(entry.evidence_ids) == expected
    assert entry.reasoning_trace is not None
    assert set(entry.reasoning_trace.evidence_ids) == expected


def test_graph_presentation_parses_strict_json_and_maps_edge_evidence() -> None:
    fixture = build_graph_read_fixture()
    version = fixture.graph_version

    presentation = build_artifact_presentation(
        ArtifactKind.graph,
        version.content,
        version.evidence,
    )

    for edge in presentation.graph_edges:
        assert set(edge.evidence_ids) == {
            item.id
            for item in version.evidence
            if item.target_type == "graph_edge" and item.target_id == edge.key
        }


def test_paper_summary_presentation_keeps_statement_evidence() -> None:
    _, version = build_demo_summary_read()

    background = next(
        section
        for section in version.presentation.sections
        if section.title == "研究背景"
    )

    assert background.paragraphs[0].evidence_ids == ("evd_papsum_03",)


def test_paper_summary_presentation_preserves_status_and_source_conflicts() -> None:
    _, version = build_demo_summary_read()
    statuses = {
        paragraph.status
        for section in version.presentation.sections
        for paragraph in section.paragraphs
    }
    assert statuses == {"supported", "unsupported", "unverifiable"}

    payload = deepcopy(version.content)
    source_evidence = payload["evidence"][0]
    payload["source_conflicts"] = [
        {
            "conflict_id": "conflict.demo-source-version",
            "evidence_id": source_evidence["evidence_id"],
            "source_snapshot_id": source_evidence["source_snapshot_id"],
            "claimed_source_version": "superseded-demo-version",
            "source_snapshot_version": source_evidence["source_snapshot_version"],
            "resolution": "source_snapshot_version_retained",
        }
    ]
    output_hash = compute_paper_summary_output_hash(payload)
    payload["output_hash"] = output_hash
    payload["producer"]["output_hash"] = output_hash

    presentation = build_artifact_presentation(
        ArtifactKind.paper_summary,
        payload,
        version.evidence,
    )
    conflict_section = next(
        section for section in presentation.sections if section.title == "来源核验"
    )
    assert conflict_section.paragraphs[0].status == "unverifiable"
    assert conflict_section.paragraphs[0].text == (
        "来源信息存在冲突，请结合原始来源核验。"
    )
    assert "superseded-demo-version" not in conflict_section.paragraphs[0].text
    assert (
        source_evidence["source_snapshot_version"]
        not in conflict_section.paragraphs[0].text
    )
    expected_evidence = next(
        item.id
        for item in version.evidence
        if item.locator.get("summary_evidence_id") == source_evidence["evidence_id"]
    )
    assert conflict_section.paragraphs[0].evidence_ids == (expected_evidence,)


def test_paper_summary_presentation_rejects_missing_persisted_evidence() -> None:
    _, version = build_demo_summary_read()
    incomplete_evidence = tuple(
        item for item in version.evidence if item.id != "evd_papsum_03"
    )

    with pytest.raises(PresentationIntegrityError):
        build_artifact_presentation(
            ArtifactKind.paper_summary,
            version.content,
            incomplete_evidence,
        )


def test_paper_collection_presentation_keeps_review_decisions() -> None:
    collection = build_demo_collection()
    presentation = build_artifact_presentation(
        ArtifactKind.paper_collection,
        collection.model_dump(mode="json"),
        (),
    )

    first = presentation.entries[0]
    assert first.status == "selected"
    assert first.external_url == str(collection.candidates[0].url)
    assert first.assessment == "相关度 0.56"
    assert collection.candidates[0].selection_reason in first.paragraphs
    facts = {fact.label: fact.values for fact in first.facts}
    assert facts["DOI"] == (collection.candidates[0].doi,)
    assert facts["重复候选"] == ("2 项",)


def test_literature_presentation_preserves_scientific_decision_fields() -> None:
    fixture = build_literature_fixture()
    version = fixture.artifacts.versions[fixture.claim_version_ids[0]]
    payload = deepcopy(version.content)
    claim = payload["claims"][0]
    claim.update(
        {
            "metric": "transit depth",
            "unit": "ppm",
            "uncertainty": "±20 ppm",
            "comparison_basis": "同一目标与同一波段",
        }
    )
    claim["fingerprint"] = compute_literature_claim_fingerprint(claim)
    output_hash = compute_literature_claims_output_hash(payload)
    payload["output_hash"] = output_hash
    payload["producer"]["output_hash"] = output_hash

    claim_presentation = build_artifact_presentation(
        ArtifactKind.literature_claims,
        payload,
        version.evidence,
    )
    claim_facts = {
        fact.label: fact.values for fact in claim_presentation.entries[0].facts
    }
    assert claim_facts["指标"] == ("transit depth",)
    assert claim_facts["单位"] == ("ppm",)
    assert claim_facts["不确定性"] == ("±20 ppm",)
    assert claim_facts["比较基准"] == ("同一目标与同一波段",)

    relation_version = fixture.artifacts.versions[fixture.relation_version_id]
    relation_presentation = build_artifact_presentation(
        ArtifactKind.literature_relations,
        relation_version.content,
        relation_version.evidence,
    )
    relation_facts = {
        fact.label: fact.values for fact in relation_presentation.entries[0].facts
    }
    assert {"对象可比性", "指标可比性", "单位可比性", "置信度"} <= set(relation_facts)
    relation_entry = relation_presentation.entries[0]
    assert relation_entry.relation is not None
    assert relation_entry.title == (
        f"{relation_entry.relation.source_claim} → "
        f"{relation_entry.relation.target_claim}"
    )

    rejected = next(
        case.admission.publisher_candidate
        for case in build_frozen_claim_benchmark_cases(load_frozen_benchmark())
        if case.case_id == "rejection.duplicate"
    )
    assert rejected is not None
    rejected_presentation = build_artifact_presentation(
        ArtifactKind.literature_claims,
        rejected.model_dump(mode="json"),
        (),
    )
    rejected_facts = {
        fact.label: fact.values for fact in rejected_presentation.entries[0].facts
    }
    assert rejected_facts["未采纳原因"] == ("内容重复",)


def test_literature_relation_adjudicable_is_single_confidence_gate() -> None:
    cases = {
        case.case_id: case
        for case in build_frozen_relation_benchmark_cases(load_frozen_benchmark())
    }
    adjudicable_relation = next(
        relation
        for relation in cases[
            "scientific.relation.clark_catalog_derived_from_tic"
        ].admission.publisher_candidate.relations
        if relation.status.value == "candidate"
    )
    accepted_relation = next(
        relation
        for relation in cases[
            "scientific.relation.revised_tic_extends_initial_tic"
        ].admission.publisher_candidate.relations
        if relation.status.value == "accepted"
    )
    assert literature_relation_adjudicable(adjudicable_relation) is True
    assert literature_relation_adjudicable(accepted_relation) is False


def test_literature_presentation_exposes_can_adjudicate() -> None:
    cases = {
        case.case_id: case
        for case in build_frozen_relation_benchmark_cases(load_frozen_benchmark())
    }
    adjudicable_presentation = build_artifact_presentation(
        ArtifactKind.literature_relations,
        cases[
            "scientific.relation.clark_catalog_derived_from_tic"
        ].admission.publisher_candidate.model_dump(mode="json"),
        (),
    )
    candidate_entry = next(
        entry
        for entry in adjudicable_presentation.entries
        if entry.status == "candidate"
    )
    assert candidate_entry.can_adjudicate is True

    accepted_presentation = build_artifact_presentation(
        ArtifactKind.literature_relations,
        cases[
            "scientific.relation.revised_tic_extends_initial_tic"
        ].admission.publisher_candidate.model_dump(mode="json"),
        (),
    )
    accepted_entry = next(
        entry
        for entry in accepted_presentation.entries
        if entry.status == "accepted"
    )
    assert accepted_entry.can_adjudicate is False
