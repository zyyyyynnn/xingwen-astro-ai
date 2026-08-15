"""Stable paper metadata canonicalization."""

from __future__ import annotations

import re
import unicodedata
import urllib.parse
from collections.abc import Sequence
from dataclasses import dataclass

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.paper_collection import RawPaperCandidate

from .sources.base import RawSourceRecord


_DOI = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)
_ARXIV = re.compile(
    r"(?:arxiv:\s*|(?:https?://)?(?:www\.)?arxiv\.org/(?:abs|pdf)/)?"
    r"(?P<id>(?:[a-z-]+(?:\.[a-z-]+)?/\d{7}|\d{4}\.\d{4,5}))(?:v\d+)?(?:\.pdf)?",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s+")
_TRACKING_PARAMETERS = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid"}
)


@dataclass(frozen=True)
class CandidateDraft:
    candidate_id: str
    raw: RawPaperCandidate
    canonical_paper_id: str
    canonical_identity_basis: str
    title: str
    normalized_title: str
    authors: tuple[str, ...]
    normalized_authors: tuple[str, ...]
    year: int | None
    doi: str | None
    arxiv_id: str | None
    url: str | None


def canonicalize_record(
    record: RawSourceRecord, *, snapshot_id: str, occurrence_index: int = 0
) -> CandidateDraft:
    title = normalize_display_text(record.title)
    normalized_title = normalize_title(title)
    authors = tuple(
        author
        for author in (normalize_display_text(value) for value in record.authors)
        if author
    )
    normalized_authors = tuple(normalize_author(author) for author in authors)
    doi = normalize_doi(record.doi)
    arxiv_id = normalize_arxiv_id(record.arxiv_id or record.url)
    url = normalize_url(record.url, doi=doi, arxiv_id=arxiv_id)
    raw_payload = record.hash_payload()
    record_hash = compute_canonical_payload_hash(raw_payload)
    raw = RawPaperCandidate(
        source_id=record.source_id,
        source_record_id=record.source_record_id,
        source_snapshot_id=snapshot_id,
        title=record.title,
        authors=record.authors,
        year=record.year,
        doi=record.doi,
        arxiv_id=record.arxiv_id,
        url=record.url,
        record_hash=record_hash,
        synthetic_note=record.synthetic_note,
    )
    candidate_hash = compute_canonical_payload_hash(
        {
            "source_id": record.source_id,
            "record_hash": record_hash,
            "occurrence_index": occurrence_index,
        }
    )
    candidate_id = f"candidate.{candidate_hash.removeprefix('sha256:')}"
    identity_basis, _ = canonical_identity(
        doi=doi,
        arxiv_id=arxiv_id,
        normalized_title=normalized_title,
        year=record.year,
        normalized_authors=normalized_authors,
        source_id=record.source_id,
        source_record_id=record.source_record_id,
    )
    return CandidateDraft(
        candidate_id=candidate_id,
        raw=raw,
        canonical_paper_id=canonical_paper_id(
            doi=doi,
            arxiv_id=arxiv_id,
            normalized_title=normalized_title,
            year=record.year,
            normalized_authors=normalized_authors,
            source_id=record.source_id,
            source_record_id=record.source_record_id,
        ),
        canonical_identity_basis=identity_basis,
        title=title,
        normalized_title=normalized_title,
        authors=authors,
        normalized_authors=normalized_authors,
        year=record.year,
        doi=doi,
        arxiv_id=arxiv_id,
        url=url,
    )


def canonicalize_records(
    records: Sequence[RawSourceRecord],
    snapshots: Sequence[SourceSnapshotRecord],
) -> tuple[CandidateDraft, ...]:
    """Canonicalize an acquired record set with deterministic occurrence ids.

    Acquisition adapters may return the same source record more than once.  A
    stable hash order and per-record occurrence counter keep candidate ids
    reproducible without making a source adapter responsible for deduping.
    """

    if not records:
        return ()
    snapshot_id_by_source = {
        snapshot.source_id: snapshot.snapshot_id for snapshot in snapshots
    }
    missing_sources = {
        record.source_id for record in records if record.source_id not in snapshot_id_by_source
    }
    if missing_sources:
        raise ValueError(
            "acquired records have no matching SourceSnapshot: "
            + ", ".join(sorted(missing_sources))
        )
    ordered = sorted(
        records,
        key=lambda record: compute_canonical_payload_hash(record.hash_payload()),
    )
    occurrences: dict[str, int] = {}
    drafts: list[CandidateDraft] = []
    for record in ordered:
        record_key = compute_canonical_payload_hash(record.hash_payload())
        occurrence = occurrences.get(record_key, 0)
        occurrences[record_key] = occurrence + 1
        drafts.append(
            canonicalize_record(
                record,
                snapshot_id=snapshot_id_by_source[record.source_id],
                occurrence_index=occurrence,
            )
        )
    return tuple(drafts)


def canonical_identity(
    *,
    doi: str | None,
    arxiv_id: str | None,
    normalized_title: str,
    year: int | None,
    normalized_authors: tuple[str, ...],
    source_id: str,
    source_record_id: str,
) -> tuple[str, object]:
    if doi:
        return "doi", doi
    if arxiv_id:
        return "arxiv_id", arxiv_id
    if normalized_title and year and normalized_authors:
        return (
            "title_year_authors",
            {
                "title": normalized_title,
                "year": year,
                "first_author": author_surname(normalized_authors[0]),
            },
        )
    return "source_record", {"source_id": source_id, "source_record_id": source_record_id}


def canonical_paper_id(
    *,
    doi: str | None,
    arxiv_id: str | None,
    normalized_title: str,
    year: int | None,
    normalized_authors: tuple[str, ...],
    source_id: str,
    source_record_id: str,
) -> str:
    """Return the one Paper identity used by every acquisition path.

    Upload-backed documents deliberately fall through to the authoritative
    source-record basis when no trustworthy bibliographic identifier exists.
    This preserves the ResearchInput provenance event without pretending that
    a matching PaperCollection candidate was observed.
    """

    identity_basis, identity = canonical_identity(
        doi=doi,
        arxiv_id=arxiv_id,
        normalized_title=normalized_title,
        year=year,
        normalized_authors=normalized_authors,
        source_id=source_id,
        source_record_id=source_record_id,
    )
    canonical_hash = compute_canonical_payload_hash(
        {"identity_basis": identity_basis, "identity": identity}
    )
    return f"paper.{canonical_hash.removeprefix('sha256:')}"


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    decoded = urllib.parse.unquote(unicodedata.normalize("NFKC", value)).strip()
    decoded = re.sub(
        r"^(?:doi\s*:\s*|https?://(?:dx\.)?doi\.org/)",
        "",
        decoded,
        flags=re.IGNORECASE,
    )
    match = _DOI.search(decoded)
    if not match:
        return None
    return match.group(0).rstrip(".,;:)]}\"").casefold()


def normalize_arxiv_id(value: str | None) -> str | None:
    if not value:
        return None
    decoded = urllib.parse.unquote(unicodedata.normalize("NFKC", value)).strip()
    match = _ARXIV.search(decoded)
    return match.group("id").casefold() if match else None


def normalize_url(
    value: str | None,
    *,
    doi: str | None = None,
    arxiv_id: str | None = None,
) -> str | None:
    if doi:
        return f"https://doi.org/{doi}"
    if arxiv_id:
        return f"https://arxiv.org/abs/{arxiv_id}"
    if not value:
        return None
    parsed = urllib.parse.urlsplit(unicodedata.normalize("NFKC", value).strip())
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return None
    query = urllib.parse.urlencode(
        sorted(
            (key, item)
            for key, item in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold() not in _TRACKING_PARAMETERS
        ),
        doseq=True,
    )
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{parsed.hostname.casefold()}{port}"
    path = parsed.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit(
        (parsed.scheme.casefold(), netloc, path, query, "")
    )


def normalize_display_text(value: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip()


def normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    without_punctuation = "".join(
        " " if unicodedata.category(character)[0] in {"P", "S"} else character
        for character in normalized
    )
    return _WHITESPACE.sub(" ", without_punctuation).strip()


def normalize_author(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    without_punctuation = "".join(
        " " if unicodedata.category(character)[0] == "P" else character
        for character in normalized
    )
    return _WHITESPACE.sub(" ", without_punctuation).strip()


def author_surname(normalized_author: str) -> str:
    parts = normalized_author.split()
    return parts[-1] if parts else ""
