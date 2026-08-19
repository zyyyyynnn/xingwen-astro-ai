"""Deterministic downloads pinned to one admitted PaperSummary ArtifactVersion."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Literal

from app.schemas.paper_summary import PaperSummaryStatement
from app.schemas.paper_summary_api import PaperSummaryRead
from app.services.paper_summaries import PaperSummaryReadService


PaperSummaryExportFormat = Literal["json", "markdown"]

_MARKDOWN_ESCAPE = re.compile(r"([\\`*{}\[\]()#+\-.!_|>])")
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_SECTIONS = (
    ("研究目标", "research_goal"),
    ("方法", "method"),
    ("数据集", "dataset"),
    ("实验与结果", "findings"),
    ("局限性", "limitations"),
    ("未来工作", "future_work"),
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
        f"# {_escape_markdown(read.paper.title)}",
        "",
        _paper_byline(read),
    ]
    for heading, field_name in _SECTIONS:
        lines.extend(("", f"## {heading}", ""))
        value = getattr(summary, field_name)
        statements = (value,) if isinstance(value, PaperSummaryStatement) else tuple(value)
        statements = tuple(item for item in statements if item is not None)
        if not statements:
            lines.append("_未收录已接纳的陈述。_")
            continue
        for statement in statements:
            lines.extend(_statement_lines(statement))
    lines.extend(
        (
            "",
            "## 证据",
            "",
            f"共 {len(read.evidence)} 条核验证据；完整机器 provenance 请使用 JSON 导出。",
        )
    )
    return "\n".join(lines) + "\n"


def _paper_byline(read: PaperSummaryRead) -> str:
    paper = read.paper
    authors = ", ".join(_escape_markdown(author) for author in paper.authors)
    parts = [authors] if authors else ["作者信息不可用"]
    if paper.year is not None:
        parts.append(str(paper.year))
    return " · ".join(parts)


def _statement_lines(statement: PaperSummaryStatement) -> tuple[str, ...]:
    lines = [f"- {_escape_markdown(statement.text)}"]
    lines.append(f"  - 支持状态：`{statement.status.value}`")
    lines.append(f"  - 证据数：{len(statement.evidence_ids)}")
    return tuple(lines)


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
