"""Testable paper source adapter boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.schemas.enums import PaperDataLevel, SourceMode, UpstreamFailureClass
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.paper_collection import NormalizedPaperQuery, PaperSourcePage


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


class HttpTransport(Protocol):
    def request(
        self,
        *,
        url: str,
        params: Mapping[str, str | int],
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse: ...


@dataclass(frozen=True)
class RawSourceRecord:
    source_id: str
    source_record_id: str
    title: str
    authors: tuple[str, ...]
    year: int | None
    doi: str | None
    arxiv_id: str | None
    url: str | None
    # Provenance label for synthetic demo/test records; live adapters never
    # set it. Excluded from hash_payload: it is a label, not scientific content.
    synthetic_note: str | None = None

    def hash_payload(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_record_id": self.source_record_id,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "url": self.url,
        }


@dataclass(frozen=True)
class SourceSearchResult:
    records: tuple[RawSourceRecord, ...]
    pages: tuple[PaperSourcePage, ...]
    snapshot: SourceSnapshotRecord
    retry_count: int


class SourceFailure(RuntimeError):
    def __init__(
        self,
        classification: UpstreamFailureClass,
        code: str,
        *,
        retryable: bool,
        status_code: int | None = None,
        attempt_count: int = 1,
    ) -> None:
        super().__init__(code)
        self.classification = classification
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.attempt_count = attempt_count


class PaperSourceAdapter(Protocol):
    source_id: str
    adapter_name: str
    adapter_version: str

    def search(
        self,
        query: NormalizedPaperQuery,
        *,
        source_mode: SourceMode,
        data_level: PaperDataLevel,
    ) -> SourceSearchResult: ...


Clock = Callable[[], datetime]
Sleeper = Callable[[float], None]
