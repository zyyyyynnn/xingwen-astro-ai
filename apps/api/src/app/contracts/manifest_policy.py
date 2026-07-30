"""Case Manifest admission for immutable core research contracts."""

from __future__ import annotations

from datetime import datetime

from app.schemas.manifest import ManifestBundle
from app.schemas.core import ResearchContract, ResearchContractInput


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


def confirm_research_contract(
    contract: ResearchContractInput,
    *,
    id: str,
    project_id: str,
    version: int,
    created_from_draft_id: str,
    created_at: datetime,
    content_hash: str,
    case_key: str,
    manifests: ManifestBundle,
) -> ResearchContract:
    """Create an immutable contract only after frozen-manifest admission."""

    validate_contract_against_manifest(
        contract,
        case_key=case_key,
        manifests=manifests,
    )
    return ResearchContract.model_validate(
        {
            **contract.model_dump(mode="python"),
            "id": id,
            "project_id": project_id,
            "version": version,
            "created_from_draft_id": created_from_draft_id,
            "created_at": created_at,
            "content_hash": content_hash,
        }
    )
