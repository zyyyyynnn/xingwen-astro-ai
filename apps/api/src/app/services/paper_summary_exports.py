"""Deterministic downloads pinned to one admitted PaperSummary ArtifactVersion."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Literal

from app.schemas.paper_summary import PaperSummarySection, PaperSummaryStatement
from app.schemas.paper_summary_api import PaperSummaryRead
from app.services.paper_summaries import PaperSummaryReadService


PaperSummaryExportFormat = Literal["json", "markdown"]

_MARKDOWN_ESCAPE = re.compile(r"([\\`*{}\[\]()#+\-.!_|>])")
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_SECTIONS = (
    ("Research Background", "background"),
    ("Methodology", "methodology"),
    ("Dataset", "dataset"),
    ("Experiments and Results", "experiments"),
    ("Discussion and Conclusions", "discussion"),
    ("Limitations", "limitations"),
    ("Research Questions", "research_questions"),
)


@dataclass(frozen=True, slots=True)
class PaperSummaryExportDownload:
    content: bytes
    media_type: str
    filename: str
    artifact_version_id: str
    content_hash: str


class PaperSummaryExportService:
    """Render one already-validated summary without resolving a mutable latest pointer."""

    def __init__(self, summaries: PaperSummaryReadService) -> None:
        self._summaries = summaries

    def export(
        self,
        *,
        version_id: str,
        session_id: str,
        export_format: PaperSummaryExportFormat,
    ) -> PaperSummaryExportDownload:
        read = self._summaries.get_summary(
            version_id=version_id,
            session_id=session_id,
        )
        safe_version = _safe_filename_component(read.artifact_version_id)
        if export_format == "json":
            content = (
                json.dumps(
                    read.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
            media_type = "application/json"
            extension = "json"
        elif export_format == "markdown":
            content = _render_markdown(read).encode("utf-8")
            media_type = "text/markdown"
            extension = "md"
        else:
            raise ValueError(f"unsupported PaperSummary export format: {export_format}")
        return PaperSummaryExportDownload(
            content=content,
            media_type=media_type,
            filename=f"paper-summary-{safe_version}.{extension}",
            artifact_version_id=read.artifact_version_id,
            content_hash=read.content_hash,
        )


def _render_markdown(read: PaperSummaryRead) -> str:
    summary = read.summary
    lines = [
        "# Paper Summary",
        "",
        f"- ArtifactVersion: `{read.artifact_version_id}`",
        f"- Artifact: `{read.artifact_id}`",
        f"- Version number: `{read.version_number}`",
        f"- Schema version: `{summary.schema_version}`",
        f"- Content hash: `{read.content_hash}`",
        f"- Paper identity: `{summary.paper_id}`",
        "",
        f"# {_escape_markdown(summary.paper.title)}",
        "",
        _paper_byline(read),
    ]
    for heading, field_name in _SECTIONS:
        lines.extend(("", f"## {heading}", ""))
        section = getattr(summary, field_name)
        statements = section.statements()
        if not statements:
            lines.append("_No admitted statements._")
            continue
        for statement in statements:
            lines.extend(_statement_lines(statement, section))
    lines.extend(("", "## Provenance", ""))
    lines.append(f"- Producer execution: `{read.producer_execution.id}`")
    lines.append(f"- Input hash: `{read.input_hash}`")
    lines.append(
        "- Source snapshots: "
        + _inline_codes(tuple(item.id for item in read.source_snapshots))
    )
    lines.append(
        "- Evidence records: " + _inline_codes(tuple(item.id for item in read.evidence))
    )
    return "\n".join(lines) + "\n"


def _paper_byline(read: PaperSummaryRead) -> str:
    paper = read.paper
    authors = ", ".join(_escape_markdown(author) for author in paper.authors)
    parts = [authors] if authors else ["Authors unavailable"]
    if paper.year is not None:
        parts.append(str(paper.year))
    return " · ".join(parts)


def _statement_lines(
    statement: PaperSummaryStatement,
    section: PaperSummarySection,
) -> tuple[str, ...]:
    role = "overview" if section.overview is statement else statement.item_kind.value
    lines = [f"- **{role}** — {_escape_markdown(statement.text)}"]
    lines.append(f"  - Support: `{statement.status.value}`")
    lines.append("  - Evidence: " + _inline_codes(statement.evidence_ids))
    return tuple(lines)


def _inline_codes(values: tuple[str, ...]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "_none_"


def _escape_markdown(value: str) -> str:
    escaped = _MARKDOWN_ESCAPE.sub(r"\\\1", value)
    return "  \n".join(escaped.splitlines())


def _safe_filename_component(value: str) -> str:
    normalized = _SAFE_FILENAME.sub("-", value).strip(".-")
    return (normalized or "version")[:96]


__all__ = [
    "PaperSummaryExportDownload",
    "PaperSummaryExportFormat",
    "PaperSummaryExportService",
]
