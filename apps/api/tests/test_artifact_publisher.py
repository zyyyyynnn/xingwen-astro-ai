"""Port-level admission and safety contracts for the B-14 publisher."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict

from app.workflow.publisher import (
    ArtifactAdmissionContext,
    ArtifactPublication,
    ProducerExecutionRequest,
    ProducerExecutionStore,
    PublicationAdmissionError,
    admit_artifact_candidate,
)


class DatasetCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rows: tuple[dict[str, str | float], ...]
    quality_score: float


class PaperSummaryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    paper_id: str
    findings: tuple[str, ...]
    evidence_ids: tuple[str, ...]


class ReasoningCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_ids: tuple[str, ...]
    relation_ids: tuple[str, ...]
    trace_ids: tuple[str, ...]


class GraphCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_ids: tuple[str, ...]
    edges: tuple[tuple[str, str, str], ...]


def _accept(_: ArtifactAdmissionContext) -> None:
    return None


@pytest.mark.parametrize(
    "candidate",
    (
        DatasetCandidate(
            rows=({"object_id": "TOI-700 d", "radius": 1.14},), quality_score=1.0
        ),
        PaperSummaryCandidate(
            paper_id="paper_01",
            findings=("Validated fixture finding",),
            evidence_ids=("evidence_01",),
        ),
        ReasoningCandidate(
            claim_ids=("claim_01",),
            relation_ids=("relation_01",),
            trace_ids=("trace_01",),
        ),
        GraphCandidate(
            node_ids=("node_01", "node_02"),
            edges=(("node_01", "supports", "node_02"),),
        ),
    ),
)
def test_representative_fixture_candidates_pass_the_typed_admission_port(
    candidate: BaseModel,
) -> None:
    admitted = admit_artifact_candidate(
        candidate,
        schema_version="2.0.0",
        source_snapshot_ids=("source_fixture_01",),
        evidence_ids=("evidence_fixture_01",),
        evidence_validator=_accept,
        domain_validator=_accept,
        quality_validator=_accept,
    )
    publication = ArtifactPublication(
        artifact_id=uuid4(),
        publication_key=f"fixture-{candidate.__class__.__name__}",
        producer_execution_id=uuid4(),
        candidate=admitted,
        source_mode="fixture",
    )

    assert publication.source_mode == "fixture"
    assert admitted.content_hash.startswith("sha256:")
    assert admitted.content == candidate.model_dump(mode="json", exclude_none=True)


@pytest.mark.parametrize("candidate", ("free text", {"untyped": "mapping"}))
def test_admission_rejects_free_text_and_untyped_mappings(candidate: object) -> None:
    with pytest.raises(PublicationAdmissionError, match="Pydantic"):
        admit_artifact_candidate(  # type: ignore[arg-type]
            candidate,
            schema_version="2.0.0",
            source_snapshot_ids=(),
            evidence_ids=(),
            evidence_validator=_accept,
            domain_validator=_accept,
            quality_validator=_accept,
        )


def test_any_failed_admission_gate_prevents_candidate_creation() -> None:
    candidate = DatasetCandidate(rows=(), quality_score=0.0)

    def reject(_: ArtifactAdmissionContext) -> None:
        raise ValueError("quality threshold failed")

    with pytest.raises(PublicationAdmissionError, match="admission failed"):
        admit_artifact_candidate(
            candidate,
            schema_version="2.0.0",
            source_snapshot_ids=("source_fixture_01",),
            evidence_ids=(),
            evidence_validator=_accept,
            domain_validator=_accept,
            quality_validator=reject,
        )


@pytest.mark.parametrize(
    "sensitive_key",
    ("api_key", "openai_api_key", "proxy_authorization", "raw_model_output"),
)
def test_producer_parameters_reject_secret_and_raw_content_fields_before_storage(
    sensitive_key: str,
) -> None:
    def unused_factory() -> Callable[[], None]:
        raise AssertionError(
            "invalid input must fail before opening a database session"
        )

    ledger = ProducerExecutionStore(unused_factory)  # type: ignore[arg-type]
    request = ProducerExecutionRequest(
        run_id=uuid4(),
        step_key="planning",
        attempt_id=uuid4(),
        idempotency_key="producer-01",
        producer_type="model",
        producer_name="qwen",
        producer_version="1.0.0",
        input_hash="sha256:" + "a" * 64,
        parameters={sensitive_key: "must-not-be-stored"},
    )

    with pytest.raises(ValueError, match="forbidden"):
        ledger.start_producer_execution(
            request,
            token=uuid4(),
            generation=1,
            expected_status="planning",
            expected_revision=3,
        )
