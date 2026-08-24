"""Single authorization authority for document-derived scientific values."""

from __future__ import annotations

from enum import StrEnum

from app.schemas.core import DocumentSourcePolicy


class DocumentAuthorizationDecision(StrEnum):
    authorized = "authorized"
    policy_disabled = "policy_disabled"
    case_capability_unsupported = "case_capability_unsupported"
    provenance_invalid = "provenance_invalid"


def authorize_document_source(
    *,
    policy: DocumentSourcePolicy,
    case_capability: bool,
    provenance_closed: bool,
) -> DocumentAuthorizationDecision:
    """Apply the Contract, Case and provenance conjunction in one place."""

    if policy is DocumentSourcePolicy.disabled:
        return DocumentAuthorizationDecision.policy_disabled
    if not case_capability:
        return DocumentAuthorizationDecision.case_capability_unsupported
    if not provenance_closed:
        return DocumentAuthorizationDecision.provenance_invalid
    return DocumentAuthorizationDecision.authorized


__all__ = ["DocumentAuthorizationDecision", "authorize_document_source"]
