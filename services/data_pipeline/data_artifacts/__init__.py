"""C-04 deterministic field mapping and data Artifact candidate builder."""

from __future__ import annotations

from app.schemas.data_artifacts import DataArtifactBuildInput, DataArtifactErrorCode
from services.data_pipeline.crossmatch.policy import (
    load_crossmatch_rule_set,
    load_crossmatch_source_policy,
    load_entity_alias_catalog,
)

from .errors import DataArtifactError
from .pipeline import build_data_artifact_candidates as _build_data_artifact_candidates


def _validate_frozen_crossmatch_handoff(input_value: DataArtifactBuildInput) -> None:
    """Require the C-08 handoff to use the repository-frozen execution policy."""

    result = input_value.crossmatch_result
    context = result.admission_context
    frozen_rule_set = load_crossmatch_rule_set()
    frozen_alias_catalog = load_entity_alias_catalog()
    frozen_source_policy = load_crossmatch_source_policy()

    frozen_context = (
        frozen_rule_set,
        frozen_alias_catalog,
        frozen_source_policy,
    )
    actual_context = (
        context.rule_set,
        context.alias_catalog,
        context.source_policy,
    )
    frozen_result_bindings = (
        frozen_rule_set.rule_set_id,
        frozen_rule_set.version,
        frozen_rule_set.content_hash,
        frozen_alias_catalog.catalog_id,
        frozen_alias_catalog.version,
        frozen_alias_catalog.content_hash,
        frozen_rule_set.producer_name,
        frozen_rule_set.producer_version,
    )
    actual_result_bindings = (
        result.rule_set_id,
        result.rule_set_version,
        result.rule_set_content_hash,
        result.alias_catalog_id,
        result.alias_catalog_version,
        result.alias_catalog_content_hash,
        result.producer_execution.producer_name,
        result.producer_execution.producer_version,
    )
    if actual_context != frozen_context or actual_result_bindings != frozen_result_bindings:
        raise DataArtifactError(
            DataArtifactErrorCode.crossmatch_result_mismatch,
            "CrossmatchResult is not bound to the repository-frozen C-08 policies",
        )


def build_data_artifact_candidates(
    input: DataArtifactBuildInput,
):
    """Build candidates only from a frozen C-08 handoff and retain replay context."""

    _validate_frozen_crossmatch_handoff(input)
    result = _build_data_artifact_candidates(input)
    for candidate in (
        result.dataset,
        result.field_dictionary,
        result.source_collection,
    ):
        # The context is process-local admission state. It is intentionally absent
        # from JSON, hashes, generated schemas, and published Artifact content.
        object.__setattr__(candidate, "_artifact_publication_context", input)
    return result


__all__ = ["build_data_artifact_candidates"]
