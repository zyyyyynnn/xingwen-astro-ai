from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from app.schemas.core import ResearchContract
from app.services.model_execution import ModelExecutionError
from app.workflow.agent_runtime import AgentActivityError
from app.workflow.research_run_worker import ResearchRunWorker, _step_started_message
from app.workflow.research_step_runtime import RunStepContext
from app.workflow.step_publication import StepPublicationFactory


def test_scientific_step_has_a_public_start_message() -> None:
    step_key = "scientific.0123456789abcdef01234567"

    message = _step_started_message(
        step_key=step_key,
        skill_id="clustering_analysis",
    )

    assert message == "正在执行聚类分析。"


def test_internal_run_failure_is_not_exposed_as_public_message() -> None:
    internal_detail = "1 validation error for SourceCollectionArtifactCandidate"

    decision = ResearchRunWorker._classify_failure(ValueError(internal_detail))

    assert decision.error_code == "RUN_EXECUTION_FAILED"
    assert decision.public_message == "研究执行遇到问题，请稍后重试。"
    assert internal_detail not in decision.public_message


def test_model_execution_failure_keeps_its_safe_public_message() -> None:
    error = ModelExecutionError(
        "MODEL_PROVIDER_TIMEOUT",
        "研究助手响应超时，请稍后重试。",
    )

    decision = ResearchRunWorker._classify_failure(error)

    assert decision.error_code == error.code
    assert decision.public_message == error.public_message
    assert decision.retryable is True


def test_model_failure_preserves_active_agent_activity() -> None:
    cause = ModelExecutionError(
        "MODEL_PROVIDER_ACCESS_DENIED",
        "研究模型暂不可用，请稍后重试。",
    )
    error = AgentActivityError(
        activity_id="tool-call-1",
        activity_kind="observation",
        activity_name="分析并验证文献证据",
        cause=cause,
    )

    decision = ResearchRunWorker._classify_failure(error)

    assert decision.error_code == cause.code
    assert decision.public_message == cause.public_message
    assert decision.activity_id == "tool-call-1"
    assert decision.activity_kind == "observation"
    assert decision.activity_name == "分析并验证文献证据"


def test_invalid_model_response_is_not_retried() -> None:
    error = ModelExecutionError(
        "MODEL_RESPONSE_INVALID",
        "研究助手返回了无法验证的结果。",
    )

    decision = ResearchRunWorker._classify_failure(error)

    assert decision.retryable is False


def test_literature_bindings_materialize_shared_evidence_per_domain_target() -> None:
    context = RunStepContext(
        run_id=UUID("00000000-0000-0000-0000-000000000001"),
        project_id=UUID("00000000-0000-0000-0000-000000000002"),
        session_id="session.test",
        contract=ResearchContract.model_validate(
            {
                "id": "contract.test",
                "project_id": "project.test",
                "version": 1,
                "content_hash": "sha256:" + "a" * 64,
                "created_from_draft_id": "draft.test",
                "created_at": "2026-08-13T00:00:00Z",
                "research_goal": "研究目标",
                "target_objects": ["host_star"],
                "data_requirements": {"unit_policy": "canonical"},
                "requested_fields": ["star.tic_id"],
                "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
                "paper_search_scope": {},
                "output_requirements": [
                    "dataset",
                    "literature_claims",
                    "reasoning_traces",
                    "graph",
                    "paper_summary",
                ],
                "evidence_requirements": {},
                "quality_constraints": {},
            }
        ),
        artifacts={},
        versions={},
    )
    references = (
        SimpleNamespace(
            side="source",
            claim_id="claim.source",
            relation_id="relation.shared",
            evidence_id="evidence.shared",
            source_snapshot_id="snapshot.shared",
        ),
        SimpleNamespace(
            side="target",
            claim_id="claim.target",
            relation_id="relation.shared",
            evidence_id="evidence.shared",
            source_snapshot_id="snapshot.shared",
        ),
    )

    def unused_factory() -> None:
        raise AssertionError("literature bindings must not open a session")

    publications = StepPublicationFactory(factory=unused_factory)  # type: ignore[arg-type]

    bindings = publications.literature_bindings(
        context,
        kind="literature_relations",
        candidate=SimpleNamespace(evidence_references=references),
    )

    assert {
        (
            item.target_type,
            item.target_id,
            item.pipeline_evidence_id,
            item.pipeline_source_snapshot_id,
        )
        for item in bindings
    } == {
        ("claim", "claim.source", "evidence.shared", "snapshot.shared"),
        ("claim", "claim.target", "evidence.shared", "snapshot.shared"),
        ("relation", "relation.shared", "evidence.shared", "snapshot.shared"),
    }
