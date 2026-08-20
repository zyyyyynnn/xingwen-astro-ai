"""Exact-version PaperSummary export tests (§39)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.schemas.core import ProducerExecutionDetail, ProducerReference
from app.schemas.paper_summary import (
    PaperSummaryArtifactContent,
    PaperSummaryEvidence,
    PaperSummaryEvidenceLocator,
    PaperSummaryInputVersions,
    PaperSummaryPaperMetadata,
    PaperSummaryProducerExecution,
    PaperSummarySourceSnapshotReference,
    PaperSummaryStatement,
    PaperSummarySupportStatus,
    compute_paper_summary_output_hash,
)
from app.schemas.paper_summary_api import PaperSummaryRead
from app.services.paper_summary_exports import PaperSummaryExportService

_HASH_S = "sha256:" + "a" * 64
_HASH_C = "sha256:" + "b" * 64
_HASH_P = "sha256:" + "c" * 64
_HASH_PARAM = "sha256:" + "d" * 64
_HASH_IN = "sha256:" + "e" * 64
_HASH_R = "sha256:" + "f" * 64


def _summary_content() -> PaperSummaryArtifactContent:
    evidence = PaperSummaryEvidence(
        evidence_id="evidence.export.01",
        paper_id="paper.export",
        candidate_id="candidate.export.01",
        source_id="source.export",
        source_record_id="record-1",
        source_snapshot_id="snapshot.export.01",
        source_snapshot_version="version-1",
        source_snapshot_content_hash=_HASH_S,
        locator=PaperSummaryEvidenceLocator(
            kind="paper_text",
            source_url="https://example.org/paper",
            section="Method",
            paragraph=2,
            text_range="0:40",
            page_index=1,
        ),
        quote_or_value="transit depth measurement",
        status=PaperSummarySupportStatus.supported,
        validation_code="evidence.supported",
    )
    goal = PaperSummaryStatement(
        statement_id="statement.export.goal",
        text="研究目标是确认凌星信号。",
        evidence_ids=(evidence.evidence_id,),
        status=PaperSummarySupportStatus.supported,
        validation_code="evidence.supported",
    )
    input_versions = PaperSummaryInputVersions(
        paper_collection_version_id="00000000-0000-4000-8000-0000000000ee",
        paper_collection_schema_version="1.0.0",
        paper_collection_output_hash=_HASH_C,
        source_snapshots=(
            PaperSummarySourceSnapshotReference(
                source_snapshot_id="snapshot.export.01",
                source_id="source.export",
                source_version="version-1",
                content_hash=_HASH_S,
            ),
        ),
    )
    started = datetime(2026, 8, 14, 0, 0, 0, tzinfo=timezone.utc)
    producer = PaperSummaryProducerExecution(
        execution_id="execution.export",
        run_id="00000000-0000-4000-8000-0000000000ff",
        producer_name="qwen-chat-completions",
        producer_version="1.0.0",
        model_name="qwen3.8-max",
        prompt_name="paper_summary",
        prompt_version="2.0.2",
        prompt_hash=_HASH_P,
        parameters_version="1.0.0",
        parameters_hash=_HASH_PARAM,
        input_versions=input_versions,
        input_hash=_HASH_IN,
        model_response_hash=_HASH_R,
        output_hash="sha256:" + "0" * 64,
        status="completed",
        started_at=started,
        finished_at=started,
        latency_ms=10,
    )
    payload = {
        "kind": "paper_summary",
        "schema_version": "2.0.0",
        "summary_id": "summary.export",
        "paper_id": "paper.export",
        "benchmark": None,
        "input_versions": input_versions.model_dump(mode="json"),
        "background": [goal.model_dump(mode="json")],
        "methodology": [],
        "dataset": [],
        "experiments": [],
        "discussion": [],
        "limitations": [],
        "research_questions": [],
        "evidence_ids": [evidence.evidence_id],
        "evidence": [evidence.model_dump(mode="json")],
        "source_conflicts": [],
        "producer": producer.model_dump(mode="json", exclude_none=True),
        "input_hash": _HASH_IN,
        "output_hash": "sha256:" + "0" * 64,
    }
    output_hash = compute_paper_summary_output_hash(payload)
    payload["output_hash"] = output_hash
    payload["producer"]["output_hash"] = output_hash
    return PaperSummaryArtifactContent.model_validate(payload)


def _read(version_id: str) -> PaperSummaryRead:
    content = _summary_content()
    return PaperSummaryRead(
        artifact_version_id=version_id,
        artifact_id="artifact.export",
        project_id="project.export",
        version_number=3,
        supersedes_version_id=None,
        source_mode="live",
        content_hash=content.output_hash,
        input_hash=_HASH_IN,
        created_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        paper=PaperSummaryPaperMetadata(
            paper_id="paper.export",
            title="Transit Confirmation Study",
            authors=("Author One", "Author Two"),
            year=2026,
        ),
        summary=content,
        cache_audits=(),
        producer_execution=ProducerExecutionDetail(
            id="execution.export",
            run_id="run.export",
            step_key="summarizing_papers",
            step_attempt_id="attempt.export",
            producer=ProducerReference(
                type="model",
                name="qwen-chat-completions",
                version="1.0.0",
                requested_model="qwen3.8-max",
            ),
            parameters={"temperature": 0},
            parameters_hash=_HASH_PARAM,
            input_hash=_HASH_IN,
            output_hash=content.output_hash,
            status="completed",
            started_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        ),
        source_snapshots=(),
        evidence=(),
    )


class _FixedReadService:
    """Return the identical committed read for the requested exact version."""

    def __init__(self) -> None:
        self.requests: list[dict[str, str]] = []
        self._read = _read("00000000-0000-4000-8000-0000000000aa")

    def get_summary(self, *, version_id: str, session_id: str) -> PaperSummaryRead:
        self.requests.append({"version_id": version_id, "session_id": session_id})
        return self._read.model_copy(update={"artifact_version_id": version_id})


def test_json_export_pins_the_exact_version_deterministically() -> None:
    service = PaperSummaryExportService(_FixedReadService())
    version_id = "00000000-0000-4000-8000-0000000000aa"

    first = service.export(
        version_id=version_id, session_id="session-1", export_format="json"
    )
    second = service.export(
        version_id=version_id, session_id="session-1", export_format="json"
    )

    assert first.content == second.content
    assert first.media_type == "application/json"
    assert first.filename == f"paper-summary-{version_id}.json"
    assert first.artifact_version_id == version_id
    payload = json.loads(first.content.decode("utf-8"))
    assert payload["artifact_version_id"] == version_id
    assert payload["content_hash"] == _read(version_id).content_hash
    # Machine provenance is present in the JSON projection.
    assert payload["summary"]["producer"]["execution_id"] == "execution.export"


def test_markdown_export_stays_readable_without_internal_identifiers() -> None:
    service = PaperSummaryExportService(_FixedReadService())
    version_id = "00000000-0000-4000-8000-0000000000bb"

    download = service.export(
        version_id=version_id, session_id="session-1", export_format="markdown"
    )

    assert download.media_type == "text/markdown"
    assert download.filename == f"paper-summary-{version_id}.md"
    text = download.content.decode("utf-8")
    assert "# Transit Confirmation Study" in text
    assert "Author One, Author Two · 2026" in text
    assert "## 研究背景" in text
    assert "研究目标是确认凌星信号。" in text
    # Internal identifiers stay out of the reading Markdown (§39).
    assert version_id not in text
    assert "execution.export" not in text
    assert _HASH_IN not in text
    assert "summary.export" not in text


def test_export_requests_the_exact_version_not_a_mutable_latest() -> None:
    read_service = _FixedReadService()
    service = PaperSummaryExportService(read_service)
    version_id = "00000000-0000-4000-8000-0000000000cc"

    service.export(
        version_id=version_id, session_id="session-2", export_format="markdown"
    )

    assert read_service.requests == [
        {"version_id": version_id, "session_id": "session-2"}
    ]


def test_unknown_export_format_is_rejected() -> None:
    service = PaperSummaryExportService(_FixedReadService())
    with pytest.raises(ValueError, match="unsupported PaperSummary export format"):
        service.export(
            version_id="00000000-0000-4000-8000-0000000000dd",
            session_id="session-3",
            export_format="yaml",  # type: ignore[arg-type]
        )
