"""Cross-language gate for the committed paper-summary fixture.

The frontend consumes ``packages/data-access/src/fixture/paper-summary.fixture.json``.
AJV can only check the generated JSON Schema shape, so this suite is the
authoritative semantic gate: the committed document must round-trip through
the real Pydantic contract models, must equal a deterministic rebuild by the
real PaperSummary pipeline, must survive the real PaperSummary API ``PaperSummaryReadService``
validation path, and intentionally broken payloads must fail validation.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_summary import PaperSummaryArtifactContent
from app.schemas.paper_summary_api import PaperSummaryRead
from app.schemas.core import ArtifactVersionDetail, ResearchArtifactDetail
from app.security import SecurityProblem
from app.services.paper_summaries import PaperSummaryReadService
from services.paper_pipeline.demo_fixture import (
    FIXTURE_OUTPUT_PATH as ACQUISITION_FIXTURE_PATH,
)
from services.paper_pipeline.demo_summary_fixture import (
    FIXTURE_OUTPUT_PATH,
    build_summary_fixture_document,
)


@pytest.fixture(scope="module")
def committed_document() -> dict[str, Any]:
    return json.loads(FIXTURE_OUTPUT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def summary_version(committed_document: dict[str, Any]) -> ArtifactVersionDetail:
    return ArtifactVersionDetail.model_validate(committed_document["artifact_version"])


@pytest.fixture(scope="module")
def collection_version() -> ArtifactVersionDetail:
    acquisition = json.loads(ACQUISITION_FIXTURE_PATH.read_text(encoding="utf-8"))
    return ArtifactVersionDetail.model_validate(acquisition["artifact_version"])


def test_committed_fixture_matches_deterministic_rebuild(
    committed_document: dict[str, Any],
) -> None:
    assert committed_document == build_summary_fixture_document(), (
        "paper-summary.fixture.json drifted from the pipeline build; "
        "regenerate with `uv run --project apps/api python -m "
        "services.paper_pipeline.demo_summary_fixture` and then run "
        "`pnpm prettier --write "
        "packages/data-access/src/fixture/paper-summary.fixture.json` "
        "(the generator writes json.dumps; prettier collapses short arrays)"
    )


def test_committed_read_passes_pydantic(committed_document: dict[str, Any]) -> None:
    read = PaperSummaryRead.model_validate(committed_document["read"])
    summary = PaperSummaryArtifactContent.model_validate(
        committed_document["read"]["summary"]
    )
    assert read.source_mode.value == "fixture"
    assert read.summary.summary_id == summary.summary_id
    assert summary.input_versions.paper_collection_version_id == "artv_papcol_01"
    assert summary.evidence_ids == tuple(
        sorted(item.evidence_id for item in summary.evidence)
    )


def test_artifact_version_identity_is_consistent_with_the_summary(
    committed_document: dict[str, Any],
    summary_version: ArtifactVersionDetail,
) -> None:
    """Mirror the PaperSummary API `_validated_summary` cross-checks: the generic
    ArtifactVersion identity must be derived from the same canonical dump."""

    version = summary_version.model_dump(mode="json", exclude_none=False)
    read = committed_document["read"]
    assert version["content"] == read["summary"]
    assert version["content_hash"] == read["content_hash"]
    assert version["content_hash"] == compute_canonical_payload_hash(version["content"])
    assert version["input_hash"] == read["summary"]["input_hash"]
    assert version["schema_version"] == read["summary"]["schema_version"]
    producer = version["producer"]
    assert producer == read["producer_execution"]["producer"]
    assert producer["name"] == read["summary"]["producer"]["producer_name"]
    assert producer["version"] == read["summary"]["producer"]["producer_version"]
    assert producer["model_name"] == read["summary"]["producer"]["model_name"]
    assert producer["prompt_hash"] == read["summary"]["producer"]["prompt_hash"]
    assert producer["parameters_hash"] == read["summary"]["producer"]["parameters_hash"]
    runtime = read["producer_execution"]
    assert runtime["step_key"] == read["summary"]["producer"]["step_key"]
    assert runtime["input_hash"] == read["summary"]["input_hash"]
    assert runtime["output_hash"] == read["content_hash"]
    assert runtime["run_id"] == version["created_by_run_id"]


def test_fixture_exercises_all_three_support_statuses(
    committed_document: dict[str, Any],
) -> None:
    summary = PaperSummaryArtifactContent.model_validate(
        committed_document["read"]["summary"]
    )
    statuses = {statement.status.value for statement in summary.statements()}
    assert statuses == {"supported", "unsupported", "unverifiable"}
    # The supported experiment result is verified against real paper_metadata.
    experiment_result = summary.experiments.items[0]
    assert experiment_result.status.value == "supported"
    evidence_by_id = {item.evidence_id: item for item in summary.evidence}
    assert all(
        evidence_by_id[item].locator.kind == "paper_metadata"
        and evidence_by_id[item].status.value == "supported"
        for item in experiment_result.evidence_ids
    )
    # The unsupported statement carries no Evidence at all.
    unsupported = next(
        item for item in summary.statements() if item.status.value == "unsupported"
    )
    assert unsupported.evidence_ids == ()
    assert unsupported.validation_code == "evidence.not_provided"
    # The unverifiable statement cites a paper_text quote the pipeline could
    # not verify against any accessible source text.
    unverifiable = next(
        item for item in summary.statements() if item.status.value == "unverifiable"
    )
    assert {
        evidence_by_id[item].validation_code for item in unverifiable.evidence_ids
    } == {"evidence.source_text_unavailable"}
    evidence_statuses = {item.status.value for item in summary.evidence}
    assert evidence_statuses == {"supported", "unverifiable"}


class _Artifacts:
    """Minimal in-memory ArtifactReadService double for the PaperSummary API path."""

    def __init__(
        self,
        summary_version: ArtifactVersionDetail,
        collection_version: ArtifactVersionDetail,
    ) -> None:
        self._versions = {
            summary_version.id: summary_version,
            collection_version.id: collection_version,
        }
        self._kinds = {
            summary_version.artifact_id: ("paper_summary", summary_version),
            collection_version.artifact_id: ("paper_collection", collection_version),
        }

    def get_version(self, *, version_id: str, session_id: str) -> ArtifactVersionDetail:
        version = self._versions.get(version_id) if session_id == "owner" else None
        if version is None:
            raise SecurityProblem(
                status=404,
                code="ARTIFACT_VERSION_NOT_FOUND",
                title="Resource not found",
                detail="Resource not found",
            )
        return version

    def get_artifact(
        self, *, artifact_id: str, session_id: str
    ) -> ResearchArtifactDetail:
        entry = self._kinds.get(artifact_id) if session_id == "owner" else None
        if entry is None:
            raise SecurityProblem(
                status=404,
                code="ARTIFACT_NOT_FOUND",
                title="Resource not found",
                detail="Resource not found",
            )
        kind, version = entry
        return ResearchArtifactDetail(
            id=artifact_id,
            project_id=version.project_id,
            kind=kind,
            title=kind,
            logical_key=f"{kind}.primary",
            created_at=version.created_at,
            latest_version_id=version.id,
            versions=(),
        )


def test_committed_read_survives_the_real_paper_summary_api_service_path(
    committed_document: dict[str, Any],
    summary_version: ArtifactVersionDetail,
    collection_version: ArtifactVersionDetail,
) -> None:
    """The fixture must be a service-valid PaperSummaryRead: the real PaperSummary API
    validators (`_validated_summary`, `_validate_input_collection`,
    `_validate_snapshots_and_evidence`) accept it unchanged."""

    service = PaperSummaryReadService(_Artifacts(summary_version, collection_version))
    read = service.get_summary(version_id=summary_version.id, session_id="owner")
    assert (
        read.model_dump(mode="json", exclude_none=False) == (committed_document["read"])
    )


def test_service_rejects_tampered_version_content_hash(
    summary_version: ArtifactVersionDetail,
    collection_version: ArtifactVersionDetail,
) -> None:
    tampered = summary_version.model_copy(update={"content_hash": "sha256:" + "0" * 64})
    service = PaperSummaryReadService(_Artifacts(tampered, collection_version))
    with pytest.raises(SecurityProblem) as excinfo:
        service.get_summary(version_id=tampered.id, session_id="owner")
    assert excinfo.value.code == "PAPER_SUMMARY_SCHEMA_INVALID"


def test_service_rejects_missing_persisted_evidence(
    summary_version: ArtifactVersionDetail,
    collection_version: ArtifactVersionDetail,
) -> None:
    tampered = summary_version.model_copy(update={"evidence": (), "evidence_ids": ()})
    service = PaperSummaryReadService(_Artifacts(tampered, collection_version))
    with pytest.raises(SecurityProblem) as excinfo:
        service.get_summary(version_id=tampered.id, session_id="owner")
    assert excinfo.value.code == "PROVENANCE_SCOPE_VIOLATION"


def _summary_payload(document: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(document["read"]["summary"]))


def test_tampered_output_hash_fails_validation(
    committed_document: dict[str, Any],
) -> None:
    payload = _summary_payload(committed_document)
    payload["output_hash"] = "sha256:" + "f" * 64
    with pytest.raises(ValidationError, match="output_hash"):
        PaperSummaryArtifactContent.model_validate(payload)


def test_supported_status_without_evidence_fails_validation(
    committed_document: dict[str, Any],
) -> None:
    payload = _summary_payload(committed_document)
    assert payload["limitations"]["items"][0]["evidence_ids"] == []
    payload["limitations"]["items"][0]["status"] = "supported"
    with pytest.raises(ValidationError, match="requires Evidence"):
        PaperSummaryArtifactContent.model_validate(payload)


def test_broken_statement_evidence_link_fails_validation(
    committed_document: dict[str, Any],
) -> None:
    payload = _summary_payload(committed_document)
    referenced = payload["background"]["overview"]["evidence_ids"][0]
    payload["evidence"] = [
        item for item in payload["evidence"] if item["evidence_id"] != referenced
    ]
    with pytest.raises(ValidationError, match="fully supported Evidence"):
        PaperSummaryArtifactContent.model_validate(payload)


def test_tampered_snapshot_version_fails_validation(
    committed_document: dict[str, Any],
) -> None:
    payload = _summary_payload(committed_document)
    payload["evidence"][0]["source_snapshot_version"] = "tampered-version"
    with pytest.raises(ValidationError, match="SourceSnapshot version"):
        PaperSummaryArtifactContent.model_validate(payload)


def test_fixture_timestamps_are_utc(committed_document: dict[str, Any]) -> None:
    read = PaperSummaryRead.model_validate(committed_document["read"])
    assert isinstance(read.created_at, datetime)
    assert read.created_at.utcoffset() is not None
    assert read.created_at.utcoffset().total_seconds() == 0
