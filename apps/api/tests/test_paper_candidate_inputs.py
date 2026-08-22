"""Pure contract and fail-closed tests for the PaperCandidate bridge."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.paper_collection_api import (
    MetadataOnlyPaperCandidateInputRequest,
    OpenAccessPaperCandidateInputRequest,
    PaperCandidateAccessEvidence,
    PaperCandidateInputBinding,
)
from app.services.paper_candidate_inputs import _normalized_access_evidence
from app.services.paper_candidate_inputs import _access_url_resource_hash
from app.security import SecurityProblem


def _evidence(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "kind": "publisher_open_access",
        "license": "CC-BY-4.0",
        "evidence_url": "https://publisher.example/paper/1?token=secret#fulltext",
        "canonical_paper_id": "paper-1",
        "resource_type": "access_url",
        "resource_identity_hash": _access_url_resource_hash(
            "https://repository.example/paper.pdf"
        ),
    }
    value.update(overrides)
    return value


def test_open_access_evidence_is_normalized_without_query_or_fragment() -> None:
    request = OpenAccessPaperCandidateInputRequest(
        mode="open_access_url",
        access_url="https://repository.example/paper.pdf",
        access_evidence=PaperCandidateAccessEvidence.model_validate(_evidence()),
    )

    evidence = _normalized_access_evidence(request, canonical_paper_id="paper-1")

    assert evidence is not None
    assert evidence.evidence_url == "https://publisher.example/paper/1"


@pytest.mark.parametrize(
    "url",
    [
        "http://publisher.example/paper",
        "https://user:password@publisher.example/paper",
        "https://publisher.example/paper#fragment",
    ],
)
def test_access_evidence_rejects_non_credential_free_https(url: str) -> None:
    request = OpenAccessPaperCandidateInputRequest(
        mode="open_access_url",
        access_url="https://repository.example/paper.pdf",
        access_evidence=PaperCandidateAccessEvidence.model_validate(
            _evidence(license="CC-BY", evidence_url=url)
        ),
    )

    if "#fragment" in url:
        # Fragments are stripped, not rejected.
        assert _normalized_access_evidence(
            request, canonical_paper_id="paper-1"
        ).evidence_url.endswith("/paper")
    else:
        with pytest.raises(SecurityProblem) as exc:
            _normalized_access_evidence(request, canonical_paper_id="paper-1")
        assert exc.value.code == "PAPER_ACCESS_NOT_PROVEN"


def test_open_access_url_rejects_user_asserted_access_kind() -> None:
    request = OpenAccessPaperCandidateInputRequest(
        mode="open_access_url",
        access_url="https://repository.example/paper.pdf",
        access_evidence=PaperCandidateAccessEvidence(
            **_evidence(
                kind="user_provided",
                license="licensed",
                evidence_url="https://example.com/proof",
            )
        ),
    )
    with pytest.raises(SecurityProblem) as exc:
        _normalized_access_evidence(request, canonical_paper_id="paper-1")
    assert exc.value.code == "PAPER_ACCESS_NOT_PROVEN"


def test_metadata_only_has_no_access_claim() -> None:
    request = MetadataOnlyPaperCandidateInputRequest(
        mode="metadata_only", reason="metadata_url_only"
    )
    assert _normalized_access_evidence(request, canonical_paper_id="paper-1") is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"canonical_paper_id": "paper-2"},
        {"resource_type": "research_input"},
        {"resource_identity_hash": "sha256:" + "f" * 64},
    ],
)
def test_access_evidence_must_bind_candidate_and_exact_url(
    overrides: dict[str, object],
) -> None:
    request = OpenAccessPaperCandidateInputRequest(
        mode="open_access_url",
        access_url="https://repository.example/paper.pdf",
        access_evidence=PaperCandidateAccessEvidence.model_validate(
            _evidence(**overrides)
        ),
    )
    with pytest.raises(SecurityProblem) as exc:
        _normalized_access_evidence(request, canonical_paper_id="paper-1")
    assert exc.value.code == "PAPER_ACCESS_RESOURCE_MISMATCH"


def test_binding_does_not_expose_duplicate_as_a_persisted_outcome() -> None:
    with pytest.raises(ValidationError):
        PaperCandidateInputBinding(
            id="binding-1",
            project_id="project-1",
            paper_collection_version_id="version-1",
            candidate_id="candidate-1",
            canonical_paper_id="paper-1",
            candidate_source_snapshot_id="snapshot-1",
            mode="metadata_only",
            outcome="duplicate",
            source_collection_status="completed",
            metadata_reason="metadata_url_only",
            created_at="2026-08-13T00:00:00Z",
        )
