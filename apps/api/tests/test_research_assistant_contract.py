from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.core import (
    ArtifactKind,
    DataRequirements,
    EvidenceRequirements,
    ModelExecutionRecord,
    ModelExecutionStatus,
    PaperSearchScope,
    PlannerDraftReady,
    PlannerOutcome,
    ResearchContractInput,
    ResearchThreadEntry,
    ResearchThreadEntryKind,
    SourceScope,
)
from app.schemas.manifest import load_manifest_bundle
from app.services.model_execution import ModelExecutionError, ModelExecutionResponse
from app.services.research import _validate_planner_outcome


_MANIFEST_ROOT = (
    Path(__file__).resolve().parents[3]
    / "services"
    / "data_pipeline"
    / "manifests"
    / "exoplanet_host_star"
)


def _contract_input() -> ResearchContractInput:
    return ResearchContractInput(
        research_goal="Integrate exoplanet candidates and host-star parameters",
        target_objects=("exoplanet_candidate",),
        data_requirements=DataRequirements(),
        requested_fields=("planet.toi_id",),
        source_scope=SourceScope(allowed_sources=("nasa_exoplanet_archive",)),
        paper_search_scope=PaperSearchScope(),
        output_requirements=(ArtifactKind.dataset,),
        evidence_requirements=EvidenceRequirements(),
        quality_constraints={},
    )


def test_planner_outcome_is_discriminated_and_draft_is_validated() -> None:
    planner_outcome = TypeAdapter(PlannerOutcome)
    output = planner_outcome.validate_python(
        {
            "outcome": "draft_ready",
            "public_analysis": "已明确研究对象、字段和来源范围。",
            "assistant_message": "我已整理出一份待确认的研究协议。",
            "warnings": [],
            "contract": _contract_input().model_dump(mode="json"),
        }
    )

    assert isinstance(output, PlannerDraftReady)
    assert output.contract.output_requirements == (ArtifactKind.dataset,)

    with pytest.raises(ValidationError):
        planner_outcome.validate_python(
            {
                "outcome": "draft_ready",
                "public_analysis": "分析",
                "assistant_message": "协议",
                "warnings": [],
                "contract": {
                    **_contract_input().model_dump(mode="json"),
                    "requested_fields": [],
                },
            }
        )


def test_planner_draft_must_pass_manifest_admission_before_persistence() -> None:
    output = PlannerDraftReady(
        outcome="draft_ready",
        public_analysis="已整理协议。",
        assistant_message="请确认协议。",
        contract=_contract_input().model_copy(
            update={"requested_fields": ("invented.observation_bias",)}
        ),
    )
    manifests = load_manifest_bundle(
        _MANIFEST_ROOT / "case-manifest.json",
        _MANIFEST_ROOT / "field-manifest.json",
    )

    with pytest.raises(ModelExecutionError) as captured:
        _validate_planner_outcome(
            output,
            case_key="exoplanet_host_star",
            manifests=manifests,
            response=ModelExecutionResponse(
                payload=output.model_dump(mode="json"),
                output_hash="sha256:" + "d" * 64,
                token_usage={"prompt_tokens": 2, "completion_tokens": 3},
                latency_ms=4,
                provider_request_id="provider-invalid-draft",
            ),
        )

    assert captured.value.code == "MODEL_RESPONSE_INVALID"
    assert captured.value.output_hash == "sha256:" + "d" * 64


def test_thread_entry_and_model_execution_are_public_safe_records() -> None:
    now = datetime.now(UTC)
    entry = ResearchThreadEntry(
        id="entry_01JEXAMPLE",
        project_id="project_01JEXAMPLE",
        sequence=1,
        kind=ResearchThreadEntryKind.user_message,
        actor="user",
        public_content="请帮我整合候选行星和宿主恒星参数。",
        structured_payload={"message_length": 20},
        created_at=now,
    )
    execution = ModelExecutionRecord(
        id="execution_01JEXAMPLE",
        project_id="project_01JEXAMPLE",
        provider="qwen",
        model="qwen-plus",
        model_revision="2026-07-01",
        prompt_name="research_contract_planner",
        prompt_version="1.0.0",
        prompt_hash="sha256:" + "a" * 64,
        prompt_snapshot="Plan a public research contract without private reasoning.",
        input_snapshot={"message": "公开研究问题"},
        output_snapshot={"outcome": "draft_ready"},
        parameters_hash="sha256:" + "b" * 64,
        parameters_snapshot={"temperature": 0},
        status=ModelExecutionStatus.succeeded,
        token_usage={"input_tokens": 10, "output_tokens": 20},
        latency_ms=120,
        provider_request_id="req-qwen-1",
        created_at=now,
        finished_at=now,
    )

    assert entry.kind is ResearchThreadEntryKind.user_message
    assert execution.status is ModelExecutionStatus.succeeded
    assert "raw" not in execution.model_dump()
    assert "secret" not in execution.model_dump_json().lower()
