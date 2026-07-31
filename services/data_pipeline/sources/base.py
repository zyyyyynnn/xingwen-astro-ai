"""Testable primary data-source adapter boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.schemas.enums import UpstreamFailureClass
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.source_acquisition import (
    DataSourceCompletion,
    DataSourcePage,
    RawDataSourceRecord,
)


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
class DataSourceAcquisitionResult:
    records: tuple[RawDataSourceRecord, ...]
    pages: tuple[DataSourcePage, ...]
    snapshot: SourceSnapshotRecord
    completion: DataSourceCompletion
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


Clock = Callable[[], datetime]
MonotonicClock = Callable[[], float]
Sleeper = Callable[[float], None]
