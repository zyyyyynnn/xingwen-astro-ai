from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.main import app
from app.schemas.dataset import ColumnInfo, DatasetResponse, QualityScore
from app.schemas.enums import (
    CaseKey,
    ClaimType,
    EvidenceType,
    LiteratureRelationType,
    PaperAcquisitionStatus,
    SourceType,
)
from app.schemas.evidence import EvidenceResponse, SourceSnapshot
from app.schemas.paper import (
    PaperAcquisitionRun,
    PaperCandidate,
    PaperItem,
    PaperSearchQuery,
    PaperSummary,
)
from app.schemas.reasoning import (
    LiteratureClaim,
    LiteratureRelation,
    ReasoningTrace,
)
from app.schemas.source import SourceRecordItem

NOW = datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)
client = TestClient(app)


EXPECTED_FIELDS: dict[type[BaseModel], set[str]] = {
    DatasetResponse: {
        "id",
        "task_id",
        "name",
        "case_key",
        "row_count",
        "field_count",
        "created_at",
        "columns",
        "rows",
        "quality_score",
    },
    ColumnInfo: {
        "name",
        "label",
        "unit",
        "description",
        "data_type",
        "required",
        "source_ids",
        "missing_rate",
        "mapping_rule",
    },
    QualityScore: {
        "task_id",
        "field_coverage",
        "missing_rate",
        "source_completeness",
        "unit_consistency",
        "paper_acquisition_reproducibility",
        "paper_summary_completeness",
        "literature_relation_evidence_rate",
        "graph_evidence_completeness",
        "reproducibility",
    },
    SourceRecordItem: {
        "id",
        "task_id",
        "type",
        "name",
        "url",
        "query",
        "retrieved_at",
        "cached",
        "license_note",
    },
    PaperSearchQuery: {
        "id",
        "task_id",
        "case_key",
        "keywords",
        "source_types",
        "query_string",
        "filters",
        "created_at",
    },
    PaperAcquisitionRun: {
        "id",
        "task_id",
        "query_id",
        "status",
        "candidate_count",
        "selected_count",
        "dedupe_rule",
        "used_cache",
        "started_at",
        "finished_at",
    },
    PaperCandidate: {
        "id",
        "task_id",
        "run_id",
        "source_record_id",
        "external_id",
        "title",
        "authors",
        "year",
        "doi",
        "arxiv_id",
        "url",
        "abstract",
        "relevance_score",
        "dedupe_key",
        "selected",
        "selection_reason",
    },
    PaperSummary: {
        "id",
        "paper_id",
        "research_goal",
        "method",
        "dataset",
        "findings",
        "limitations",
        "future_work",
        "evidence_ids",
        "model_name",
        "prompt_version",
    },
    PaperItem: {
        "id",
        "candidate_id",
        "task_id",
        "title",
        "authors",
        "year",
        "url",
        "source_ids",
        "summary",
        "evidence_ids",
    },
    LiteratureClaim: {
        "id",
        "task_id",
        "paper_id",
        "claim_type",
        "text",
        "normalized_text",
        "evidence_ids",
        "confidence",
    },
    LiteratureRelation: {
        "id",
        "task_id",
        "source_claim_id",
        "target_claim_id",
        "relation_type",
        "reasoning_trace_id",
        "evidence_ids",
        "confidence",
    },
    ReasoningTrace: {
        "id",
        "task_id",
        "relation_id",
        "steps",
        "evidence_ids",
        "model_name",
        "prompt_version",
    },
    EvidenceResponse: {
        "id",
        "task_id",
        "type",
        "source_id",
        "paper_id",
        "target_type",
        "target_id",
        "content",
        "locator",
        "quote_or_value",
        "extraction_method",
        "source_snapshot",
        "confidence",
        "created_at",
    },
    SourceSnapshot: {"retrieved_at", "query_hash"},
}


EXPECTED_REQUIRED: dict[type[BaseModel], set[str]] = {
    DatasetResponse: {
        "dataset_id",
        "task_id",
        "name",
        "case_key",
        "row_count",
        "field_count",
        "created_at",
        "columns",
        "rows",
    },
    ColumnInfo: {
        "name",
        "label",
        "unit",
        "description",
        "data_type",
        "required",
        "source_ids",
        "missing_rate",
        "mapping_rule",
    },
    QualityScore: {
        "task_id",
        "field_coverage",
        "missing_rate",
        "source_completeness",
        "unit_consistency",
        "paper_acquisition_reproducibility",
        "paper_summary_completeness",
        "literature_relation_evidence_rate",
        "graph_evidence_completeness",
        "reproducibility",
    },
    SourceRecordItem: {
        "id",
        "task_id",
        "type",
        "name",
        "url",
        "query",
        "retrieved_at",
    },
    PaperSearchQuery: {
        "query_id",
        "task_id",
        "case_key",
        "keywords",
        "source_types",
        "query_string",
        "filters",
        "created_at",
    },
    PaperAcquisitionRun: {
        "run_id",
        "task_id",
        "query_id",
        "status",
        "candidate_count",
        "selected_count",
        "dedupe_rule",
        "used_cache",
        "started_at",
    },
    PaperCandidate: {
        "candidate_id",
        "task_id",
        "run_id",
        "source_record_id",
        "title",
        "authors",
        "relevance_score",
        "dedupe_key",
        "selected",
    },
    PaperSummary: {
        "id",
        "paper_id",
        "research_goal",
        "method",
        "dataset",
        "findings",
        "limitations",
        "future_work",
        "evidence_ids",
        "model_name",
        "prompt_version",
    },
    PaperItem: {
        "paper_id",
        "candidate_id",
        "task_id",
        "title",
        "authors",
        "source_ids",
    },
    LiteratureClaim: {
        "claim_id",
        "task_id",
        "paper_id",
        "claim_type",
        "text",
        "normalized_text",
        "evidence_ids",
        "confidence",
    },
    LiteratureRelation: {
        "relation_id",
        "task_id",
        "source_claim_id",
        "target_claim_id",
        "relation_type",
        "reasoning_trace_id",
        "evidence_ids",
        "confidence",
    },
    ReasoningTrace: {
        "trace_id",
        "task_id",
        "relation_id",
        "steps",
        "evidence_ids",
        "model_name",
        "prompt_version",
    },
    EvidenceResponse: {
        "id",
        "task_id",
        "type",
        "target_type",
        "target_id",
        "extraction_method",
        "source_snapshot",
        "confidence",
        "created_at",
    },
    SourceSnapshot: {"retrieved_at"},
}

EXPECTED_ID_ALIASES = {
    DatasetResponse: "dataset_id",
    PaperSearchQuery: "query_id",
    PaperAcquisitionRun: "run_id",
    PaperCandidate: "candidate_id",
    PaperItem: "paper_id",
    LiteratureClaim: "claim_id",
    LiteratureRelation: "relation_id",
    ReasoningTrace: "trace_id",
}


@pytest.mark.parametrize("model, expected", EXPECTED_FIELDS.items())
def test_exact_python_field_sets(model: type[BaseModel], expected: set[str]) -> None:
    assert set(model.model_fields) == expected


@pytest.mark.parametrize("model, expected", EXPECTED_REQUIRED.items())
def test_exact_json_schema_required_sets(
    model: type[BaseModel], expected: set[str]
) -> None:
    assert set(model.model_json_schema().get("required", [])) == expected


def test_v1_id_aliases_are_used_for_input_output_and_json_schema() -> None:
    model = PaperSearchQuery(
        query_id="query_1",
        task_id="task_1",
        case_key="exoplanet_host_star",
        keywords=["exoplanet"],
        source_types=["paper_source"],
        filters={},
        query_string="exoplanet",
        created_at=NOW,
    )
    assert model.id == "query_1"
    assert model.model_dump()["query_id"] == "query_1"
    assert "id" not in model.model_dump()
    assert "query_id" in PaperSearchQuery.model_json_schema()["properties"]

    by_domain_name = PaperSearchQuery(
        id="query_1",
        task_id="task_1",
        case_key="exoplanet_host_star",
        keywords=["exoplanet"],
        source_types=["paper_source"],
        filters={},
        query_string="exoplanet",
        created_at=NOW,
    )
    assert by_domain_name == model


@pytest.mark.parametrize("model, alias", EXPECTED_ID_ALIASES.items())
def test_all_v1_id_aliases_are_frozen(model: type[BaseModel], alias: str) -> None:
    assert model.model_fields["id"].alias == alias
    schema = model.model_json_schema()
    assert alias in schema["properties"]
    assert "id" not in schema["properties"]


def test_core_enum_values_are_frozen() -> None:
    assert {item.value for item in CaseKey} == {"exoplanet_host_star"}
    assert {item.value for item in SourceType} == {
        "database",
        "paper_source",
        "paper",
        "cache",
        "manual_review",
    }
    assert {item.value for item in PaperAcquisitionStatus} == {
        "pending",
        "running",
        "completed",
        "failed",
        "cached",
    }
    assert {item.value for item in ClaimType} == {
        "goal",
        "method",
        "dataset",
        "finding",
        "limitation",
        "future_work",
    }
    assert {item.value for item in LiteratureRelationType} == {
        "supports",
        "extends",
        "derived_from",
        "limits",
        "contradicts",
        "uses_same_dataset",
        "compares_method",
    }
    assert {item.value for item in EvidenceType} == {
        "database_query",
        "paper_search",
        "paper_metadata",
        "paper_text",
        "model_extraction",
        "reasoning_trace",
        "user_feedback",
        "cache_record",
    }


def test_required_provenance_cannot_be_silently_defaulted() -> None:
    with pytest.raises(ValidationError):
        PaperSearchQuery(
            query_id="query_1",
            keywords=["exoplanet"],
            query_string="exoplanet",
        )


def test_evidence_bound_models_reject_empty_evidence() -> None:
    with pytest.raises(ValidationError):
        PaperSummary(
            id="summary_1",
            paper_id="paper_1",
            research_goal="goal",
            method="method",
            dataset="dataset",
            findings=[],
            limitations=[],
            future_work=[],
            evidence_ids=[],
            model_name="fixture",
            prompt_version="v1",
        )


def test_v1_http_wire_keeps_legacy_ids_and_required_provenance() -> None:
    dataset = client.get("/api/tasks/task_001/dataset")
    assert dataset.status_code == 200
    dataset_data = dataset.json()["data"]
    assert dataset_data["dataset_id"] == "dataset_001"
    assert "id" not in dataset_data
    assert dataset_data["task_id"] == "task_001"
    assert dataset_data["row_count"] == len(dataset_data["rows"])
    assert dataset_data["field_count"] == len(dataset_data["columns"])
    assert all(column["mapping_rule"] for column in dataset_data["columns"])

    sources = client.get("/api/tasks/task_001/sources")
    assert sources.status_code == 200
    assert all(
        source["task_id"] == "task_001" for source in sources.json()["data"]["sources"]
    )

    acquisition = client.get("/api/tasks/task_001/paper-acquisition")
    assert acquisition.status_code == 200
    data = acquisition.json()["data"]
    assert data["query"]["query_id"] == "paper_query_001"
    assert "id" not in data["query"]
    assert data["query"]["task_id"] == "task_001"
    assert data["run"]["run_id"] == "paper_run_001"
    assert data["run"]["query_id"] == "paper_query_001"
    assert all(candidate["candidate_id"] for candidate in data["candidates"])

    reasoning = client.get("/api/tasks/task_001/literature-reasoning")
    assert reasoning.status_code == 200
    reasoning_data = reasoning.json()["data"]
    assert reasoning_data["claims"][0]["claim_id"] == "claim_001"
    assert reasoning_data["relations"][0]["relation_id"] == "relation_001"
    assert reasoning_data["traces"][0]["trace_id"] == "trace_001"
    assert all(item["task_id"] == "task_001" for item in reasoning_data["claims"])

    evidence = client.get("/api/tasks/task_001/evidence/evidence_001")
    assert evidence.status_code == 200
    evidence_data = evidence.json()["data"]
    assert evidence_data["task_id"] == "task_001"
    assert evidence_data["source_snapshot"]["retrieved_at"]


def test_generated_manifest_covers_phase0_and_crossmatch_models() -> None:
    manifest_path = (
        Path(__file__).parents[3]
        / "packages"
        / "schemas"
        / "generated"
        / "phase0"
        / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = {entry["name"] for entry in manifest["models"]}
    assert names == {
        "ColumnInfo",
        "DatasetResponse",
        "PaperSearchQuery",
        "PaperAcquisitionRun",
        "PaperCandidate",
        "PaperSummary",
        "LiteratureClaim",
        "LiteratureRelation",
        "ReasoningTrace",
        "EvidenceResponse",
        "SourceSnapshot",
        "SourceRecordItem",
        "QualityScore",
        "DataSourceCompletion",
        "CrossmatchInput",
        "CrossmatchResult",
            "CrossmatchBenchmarkManifest",
            "CrossmatchBenchmarkReport",
            "DataArtifactBuildInput",
            "DatasetArtifactCandidate",
            "FieldDictionaryArtifactCandidate",
            "SourceCollectionArtifactCandidate",
            "MappingRuleSet",
            "UnitConversionCatalog",
        }
