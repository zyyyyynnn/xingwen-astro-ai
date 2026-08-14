from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.contracts.core import create_contract_app
from app.contracts.manifest_policy import (
    validate_research_contract_admission,
    validate_contract_against_manifest,
)
from app.schemas.core import (
    ArtifactVersion,
    CollectionEnvelope,
    CreateRunRequest,
    Envelope,
    ExecutionMode,
    ProblemDetails,
    ResearchArtifact,
    ResearchContract,
    ResearchContractDraft,
    ResearchContractInput,
    ResearchProject,
    ResearchRun,
    RunEvent,
    RunStatus,
    SourceMode,
    compute_research_contract_content_hash,
)
from app.schemas.manifest import load_manifest_bundle
from app.security import canonical_request_hash
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_ROOT = REPO_ROOT / "services/data_pipeline/manifests/exoplanet_host_star"
NOW = datetime(2026, 7, 21, tzinfo=UTC)
HASH = "sha256:" + "a" * 64


def contract_input() -> dict[str, object]:
    return {
        "research_goal": "Integrate exoplanet candidates and host-star parameters",
        "target_objects": ["exoplanet_candidate", "host_star"],
        "data_requirements": {"unit_policy": "canonical"},
        "requested_fields": ["planet.toi_id", "star.tic_id"],
        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
        "paper_search_scope": {"year_from": 2015, "max_candidates": 20},
        "output_requirements": ["dataset", "field_dictionary", "graph"],
        "evidence_requirements": {"require_locator": True},
        "quality_constraints": {"source_completeness_min": 1.0},
    }


def core_examples() -> dict[type[object], dict[str, object]]:
    contract = contract_input()
    return {
        ResearchProject: {
            "id": "proj_01J",
            "session_id": "sess_01J",
            "name": "Exoplanet host-star integration",
            "case_key": "exoplanet_host_star",
            "thread_summary": {
                "has_thread_entries": False,
                "latest_thread_actor": None,
                "has_unanswered_clarification": False,
            },
            "created_at": NOW,
            "updated_at": NOW,
            "revision": 1,
        },
        ResearchContractDraft: {
            "id": "rcd_01J",
            "project_id": "proj_01J",
            "session_id": "sess_01J",
            "version": 1,
            "intent": "Integrate exoplanet candidates and host-star parameters",
            "contract": contract,
            "created_at": NOW,
            "updated_at": NOW,
            "expires_at": NOW + timedelta(hours=1),
        },
        ResearchContract: {
            **contract,
            "id": "rc_01J",
            "project_id": "proj_01J",
            "version": 1,
            "created_from_draft_id": "rcd_01J",
            "created_at": NOW,
            "content_hash": HASH,
        },
        ResearchRun: {
            "id": "run_01J",
            "project_id": "proj_01J",
            "contract_id": "rc_01J",
            "execution_mode": "live",
            "status": "queued",
            "progress": 0,
            "parent_run_id": None,
            "derivation_kind": "original",
            "retry_from_step": None,
            "cache_policy": "disabled",
            "created_at": NOW,
            "updated_at": NOW,
        },
        RunEvent: {
            "run_id": "run_01J",
            "sequence": 1,
            "event_type": "run.queued",
            "progress": 0,
            "public_message": "Run queued",
            "occurred_at": NOW,
        },
        ResearchArtifact: {
            "id": "art_01J",
            "project_id": "proj_01J",
            "kind": "dataset",
            "title": "Exoplanet host-star dataset",
            "logical_key": "dataset.primary",
            "created_at": NOW,
        },
        ArtifactVersion: {
            "id": "artv_01J",
            "artifact_id": "art_01J",
            "project_id": "proj_01J",
            "created_by_run_id": "run_01J",
            "version_number": 1,
            "schema_version": "2.0.0",
            "content": {
                "kind": "dataset",
                "field_ids": ["planet.toi_id"],
                "rows": [],
            },
            "content_hash": HASH,
            "input_hash": HASH,
            "source_mode": "live",
            "producer": {"type": "pipeline", "name": "data", "version": "1.0.0"},
            "created_at": NOW,
        },
    }


def test_seven_core_resources_validate_examples_and_forbid_extra_fields() -> None:
    examples = core_examples()
    assert len(examples) == 7
    for model, example in examples.items():
        instance = model.model_validate(example)  # type: ignore[attr-defined]
        wire = instance.model_dump(mode="json")  # type: ignore[attr-defined]
        assert model.model_validate(wire) == instance  # type: ignore[attr-defined]
        schema_examples = model.model_json_schema()["examples"]  # type: ignore[attr-defined]
        assert len(schema_examples) == 1
        model.model_validate(schema_examples[0])  # type: ignore[attr-defined]
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            model.model_validate({**example, "unexpected": True})  # type: ignore[attr-defined]


def test_contract_has_no_execution_mode_and_manifest_admission_is_authoritative() -> (
    None
):
    example = core_examples()[ResearchContract]
    contract = ResearchContract.model_validate(example)
    assert "execution_mode" not in ResearchContract.model_fields

    manifests = load_manifest_bundle(
        MANIFEST_ROOT / "case-manifest.json",
        MANIFEST_ROOT / "field-manifest.json",
    )
    validate_contract_against_manifest(
        contract,
        case_key="exoplanet_host_star",
        manifests=manifests,
    )

    admitted = ResearchContractInput.model_validate(contract_input())
    validate_research_contract_admission(
        admitted,
        content_hash=compute_research_contract_content_hash(admitted),
        case_key="exoplanet_host_star",
        manifests=manifests,
    )
    assert admitted.requested_fields == ("planet.toi_id", "star.tic_id")

    invalid = contract.model_copy(update={"requested_fields": ("planet.unknown",)})
    with pytest.raises(ValueError, match="unsupported requested field"):
        validate_contract_against_manifest(
            invalid,
            case_key="exoplanet_host_star",
            manifests=manifests,
        )

    invalid_input = ResearchContractInput.model_validate(
        {**contract_input(), "requested_fields": ["planet.unknown"]}
    )
    with pytest.raises(ValueError, match="unsupported requested field"):
        validate_research_contract_admission(
            invalid_input,
            content_hash=HASH,
            case_key="exoplanet_host_star",
            manifests=manifests,
        )


def test_fixture_contract_hash_matches_pydantic_canonical_payload() -> None:
    payload = {
        "research_goal": "Integrate exoplanet candidates and host-star parameters",
        "target_objects": ["exoplanet_candidate", "host_star"],
        "data_requirements": {"unit_policy": "canonical"},
        "requested_fields": ["planet.toi_id", "star.tic_id"],
        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
        "paper_search_scope": {
            "keywords": ["exoplanet", "host star parameters"],
            "year_from": 2018,
            "year_to": 2026,
            "source_ids": ["nasa_exoplanet_archive"],
            "max_candidates": 5,
        },
        "output_requirements": ["dataset", "graph"],
        "evidence_requirements": {
            "require_locator": True,
            "require_source_snapshot": True,
            "minimum_coverage": 1,
        },
        "quality_constraints": {
            "source_completeness_min": 1,
            "unit_consistency_min": 1,
        },
    }
    normalized = ResearchContractInput.model_validate(payload).model_dump(mode="json")

    assert normalized["evidence_requirements"]["minimum_coverage"] == 1.0
    assert canonical_request_hash(normalized) == (
        "sha256:d43c90e165cbe6b068f2c95247703ff5bfed6e371a4826831afa17ee733b9986"
    )
    assert compute_research_contract_content_hash(
        ResearchContractInput.model_validate(payload)
    ) == canonical_request_hash(normalized)


def test_contract_content_identity_projects_full_contract_to_input_payload() -> None:
    input_value = ResearchContractInput.model_validate(contract_input())
    expected = compute_research_contract_content_hash(input_value)
    first = ResearchContract.model_validate(
        {
            **input_value.model_dump(mode="json"),
            "id": "rc_first",
            "project_id": "project_first",
            "version": 1,
            "created_from_draft_id": "draft_first",
            "created_at": NOW,
            "content_hash": expected,
        }
    )
    second = first.model_copy(
        update={
            "id": "rc_second",
            "project_id": "project_second",
            "version": 9,
            "created_from_draft_id": "draft_second",
            "created_at": NOW + timedelta(hours=2),
        }
    )

    assert compute_research_contract_content_hash(first) == expected
    assert compute_research_contract_content_hash(second) == expected


def test_contract_rejects_whitespace_goal() -> None:
    with pytest.raises(ValidationError, match="string_too_short"):
        ResearchContractInput.model_validate(
            {**contract_input(), "research_goal": "    "}
        )


def test_execution_source_and_run_status_enums_preserve_domain_vocabulary() -> None:
    assert set(ExecutionMode) == {ExecutionMode.demo_replay, ExecutionMode.live}
    assert set(SourceMode) == {SourceMode.fixture, SourceMode.live, SourceMode.cached}
    run_statuses = {value.value for value in RunStatus}
    assert run_statuses == {
        "queued",
        "planning",
        "fetching_data",
        "cleaning_data",
        "searching_papers",
        "summarizing_papers",
        "reasoning_literature",
        "building_graph",
        "waiting_for_input",
        "completed",
        "failed",
        "cancelled",
    }


def test_run_terminal_progress_and_time_invariants() -> None:
    example = core_examples()[ResearchRun]
    with pytest.raises(ValidationError, match="completed run must have progress 100"):
        ResearchRun.model_validate({**example, "status": "completed", "progress": 99})
    with pytest.raises(ValidationError, match="timezone_aware"):
        ResearchRun.model_validate({**example, "created_at": "2026-07-21T08:00:00"})
    with pytest.raises(ValidationError, match="derived run must have parent_run_id"):
        ResearchRun.model_validate({**example, "derivation_kind": "retry"})
    with pytest.raises(ValidationError, match="retry_from_step is only valid"):
        ResearchRun.model_validate({**example, "retry_from_step": "fetching_data"})


def test_create_run_request_rejects_unimplemented_capability_fields() -> None:
    base = {
        "contract_id": "rc_01J",
        "execution_mode": "live",
    }
    CreateRunRequest.model_validate(base)
    assert set(CreateRunRequest.model_fields) == {"contract_id", "execution_mode"}
    for field, value in {
        "feedback_ids": ["feedback_01J"],
        "retry_from_step": "fetching_data",
        "cache_policy": "disabled",
        "parent_run_id": "run_01J",
        "derivation_kind": "retry",
    }.items():
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            CreateRunRequest.model_validate({**base, field: value})


def test_artifact_version_content_is_the_persisted_json_boundary() -> None:
    example = core_examples()[ArtifactVersion]
    version = ArtifactVersion.model_validate(example)
    assert version.content["kind"] == "dataset"
    assert ArtifactVersion.model_validate(
        {**example, "content": {"kind": "unknown", "rows": []}}
    ).content == {"kind": "unknown", "rows": []}


def test_openapi_31_has_stable_unique_operation_ids_and_transport_primitives() -> None:
    document = create_contract_app().openapi()
    assert document["openapi"].startswith("3.1.")
    operation_ids = [
        operation["operationId"]
        for path_item in document["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    assert len(operation_ids) == len(set(operation_ids))
    assert {
        "listResearchProjects",
        "createResearchProject",
        "getResearchProject",
        "updateResearchProject",
        "deleteResearchProject",
        "getResearchPlanningCatalog",
        "listResearchTurns",
        "submitResearchTurn",
        "createResearchContractDraft",
        "getResearchContractDraft",
        "updateResearchContractDraft",
        "getResearchContract",
        "confirmResearchContract",
        "getResearchRun",
        "listRunSteps",
        "createResearchRun",
        "listRunEvents",
        "listRunArtifacts",
        "getResearchArtifact",
        "getArtifactVersion",
        "createUserFeedback",
        "getUserFeedback",
        "createRevisionPlan",
        "getRevisionPlan",
        "confirmRevisionPlan",
        "getPaperCollection",
        "getPaperSummary",
        "getGraphArtifact",
        "listGraphNodes",
        "getGraphNode",
        "listGraphEdges",
        "getGraphEdge",
        "listLiteratureClaims",
        "getLiteratureClaim",
        "listLiteratureRelations",
        "getLiteratureRelation",
        "listReasoningTraces",
        "getReasoningTrace",
        "listPaperCollectionCandidates",
        "createPaperCandidateResearchInput",
        "getEvidence",
        "getSourceSnapshot",
        "createAnonymousSession",
        "getAnonymousSession",
        "revokeAnonymousSession",
        "getWorkspaceSnapshot",
        "putWorkspaceSnapshot",
        "listShareSnapshots",
        "createShareSnapshot",
        "revokeShareSnapshot",
        "getPublicShareSnapshot",
        "createResearchInput",
        "listResearchInputs",
        "getResearchInput",
        "deleteResearchInput",
        "bindResearchInput",
    } == set(operation_ids)

    create_run = document["paths"]["/api/projects/{project_id}/runs"]["post"]
    parameters = {
        parameter["name"]: parameter for parameter in create_run["parameters"]
    }
    assert parameters["Idempotency-Key"]["required"] is True
    create_project = document["paths"]["/api/projects"]["post"]
    create_project_parameters = {
        parameter["name"]: parameter for parameter in create_project["parameters"]
    }
    assert create_project_parameters["Idempotency-Key"]["required"] is True
    create_draft = document["paths"]["/api/projects/{project_id}/contract-drafts"][
        "post"
    ]
    create_draft_parameters = {
        parameter["name"]: parameter for parameter in create_draft["parameters"]
    }
    assert create_draft_parameters["Idempotency-Key"]["required"] is True
    list_projects = document["paths"]["/api/projects"]["get"]
    assert {parameter["name"] for parameter in list_projects["parameters"]} >= {
        "cursor",
        "limit",
    }
    update_draft = document["paths"]["/api/contracts/drafts/{draft_id}"]["patch"]
    update_parameters = {
        parameter["name"]: parameter for parameter in update_draft["parameters"]
    }
    assert update_parameters["If-Match"]["required"] is True
    assert "patch" not in document["paths"]["/api/contracts/{contract_id}"]
    events = document["paths"]["/api/runs/{run_id}/events"]["get"]
    assert {parameter["name"] for parameter in events["parameters"]} >= {
        "cursor",
        "limit",
    }
    assert "409" in create_run["responses"]
    assert set(create_run["responses"]["409"]["content"]) == {
        "application/problem+json"
    }
    assert "ProblemDetails" in document["components"]["schemas"]
    artifacts = document["paths"]["/api/runs/{run_id}/artifacts"]["get"]
    assert {item["name"] for item in artifacts["parameters"]} == {
        "run_id",
        "kind",
        "cursor",
        "limit",
    }
    assert artifacts["parameters"][-1]["schema"]["maximum"] == 100
    assert "/api/evidence/{evidence_id}" in document["paths"]
    assert "/api/source-snapshots/{snapshot_id}" in document["paths"]
    paper_summary = document["paths"][
        "/api/artifact-versions/{version_id}/paper-summary"
    ]["get"]
    assert paper_summary["operationId"] == "getPaperSummary"
    assert "PaperSummaryRead" in json.dumps(paper_summary)
    literature_relations = document["paths"][
        "/api/artifact-versions/{version_id}/literature-relations"
    ]["get"]
    assert {parameter["name"] for parameter in literature_relations["parameters"]} == {
        "version_id",
        "status",
        "cursor",
        "limit",
    }
    assert literature_relations["parameters"][-1]["schema"]["maximum"] == 100
    assert "LiteratureRelationRead" in json.dumps(literature_relations)
    assert "413" in literature_relations["responses"]

    workspace_put = document["paths"]["/api/projects/{project_id}/workspace-snapshot"][
        "put"
    ]
    workspace_headers = {
        parameter["name"]: parameter for parameter in workspace_put["parameters"]
    }
    assert workspace_headers["If-Match"]["required"] is True
    assert workspace_headers["X-CSRF-Token"]["required"] is True
    share_create = document["paths"]["/api/projects/{project_id}/shares"]["post"]
    assert {parameter["name"] for parameter in share_create["parameters"]} >= {
        "X-CSRF-Token"
    }


def test_envelope_cursor_and_problem_details_are_strict_schemas() -> None:
    envelope_schema = Envelope[ResearchProject].model_json_schema()
    collection_schema = CollectionEnvelope[RunEvent].model_json_schema()
    problem_schema = ProblemDetails.model_json_schema()
    assert set(envelope_schema["required"]) == {"data", "meta", "links"}
    assert "page" in collection_schema["required"]
    assert set(problem_schema["required"]) >= {
        "type",
        "title",
        "status",
        "detail",
        "instance",
        "code",
        "request_id",
    }


def test_openapi_document_is_json_serializable() -> None:
    json.dumps(create_contract_app().openapi(), ensure_ascii=False)
