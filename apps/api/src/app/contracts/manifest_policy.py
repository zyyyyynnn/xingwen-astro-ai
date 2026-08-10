"""Case Manifest admission for immutable core research contracts."""

from __future__ import annotations

from app.schemas.manifest import ManifestBundle
from app.schemas.core import (
    ResearchContract,
    ResearchContractInput,
    compute_research_contract_content_hash,
)


def validate_contract_against_manifest(
    contract: ResearchContract | ResearchContractInput,
    *,
    case_key: str,
    manifests: ManifestBundle,
) -> None:
    """Reject contract values outside the one pinned Case/Field Manifest bundle."""

    if case_key != manifests.case_manifest.case_id:
        raise ValueError(f"unsupported case_key: {case_key}")

    supported_objects = {target.role for target in manifests.case_manifest.target_objects}
    unknown_objects = sorted(set(contract.target_objects) - supported_objects)
    if unknown_objects:
        raise ValueError(f"unsupported target object(s): {unknown_objects}")

    manifests.validate_requested_fields(contract.requested_fields)
    manifests.resolve_source_scope(contract.source_scope.allowed_sources)


def validate_research_contract_admission(
    contract: ResearchContractInput,
    *,
    content_hash: str,
    case_key: str,
    manifests: ManifestBundle,
) -> None:
    """Validate frozen-manifest admission and the canonical content identity."""

    validate_contract_against_manifest(
        contract,
        case_key=case_key,
        manifests=manifests,
    )
    expected_hash = compute_research_contract_content_hash(contract)
    if content_hash != expected_hash:
        raise ValueError(
            f"ResearchContract content_hash does not match ResearchContractInput: {expected_hash}"
        )
