"""Load the exact confirmed data RevisionPlan context before any producer runs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    ResearchArtifactModel,
    ResearchRunModel,
    RevisionPlanConfirmationModel,
    RevisionPlanFeedbackModel,
    RevisionPlanModel,
    RevisionPlanVersionModel,
)
from app.schemas.data_artifacts import (
    DataArtifactBuildResult,
    compute_data_artifact_output_hash,
    compute_data_artifact_public_payload_hash,
)
from app.services.artifacts import ArtifactReadService
from app.services.data_artifact_build_inputs import (
    DataArtifactBuildInputReplayError,
    DataArtifactBuildInputRepository,
)
from app.services.data_artifacts import DataArtifactReadService
from app.services.revision_plan_hash import compute_revision_plan_hash
from services.data_pipeline.crossmatch.policy import (
    load_crossmatch_rule_set,
    load_crossmatch_source_policy,
    load_entity_alias_catalog,
)
from services.data_pipeline.data_artifacts.policy import (
    load_mapping_rule_set,
    load_unit_conversion_catalog,
)
from services.data_pipeline.data_quality.policy import load_frozen_quality_rule_set
from services.data_pipeline.revision import (
    DataRevisionArtifactBaseline,
    DataRevisionError,
    DataRevisionErrorCode,
    DataRevisionExecutionInput,
)


_DATA_KINDS = ("dataset", "field_dictionary", "source_collection")


@dataclass(frozen=True, slots=True)
class RevisionRunContext:
    artifacts: dict[str, UUID]
    versions: dict[str, UUID]
    data_execution: DataRevisionExecutionInput | None


class DataRevisionContextLoader:
    """Resolve one revision Run only through its one-to-one confirmation."""

    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory
        self._reads = DataArtifactReadService(ArtifactReadService(factory))
        self._build_inputs = DataArtifactBuildInputRepository(factory)

    def load(
        self,
        *,
        run_id: UUID,
        session_id: str,
    ) -> RevisionRunContext | None:
        with self._factory() as session, session.begin():
            run = session.get(ResearchRunModel, run_id)
            if run is None:
                raise ValueError("ResearchRun not found")
            confirmation = session.scalar(
                select(RevisionPlanConfirmationModel).where(
                    RevisionPlanConfirmationModel.run_id == run.id
                )
            )
            if run.derivation_kind != "revision":
                if confirmation is not None:
                    raise DataRevisionError(
                        DataRevisionErrorCode.replan_required,
                        "a non-revision Run is bound to a RevisionPlan",
                    )
                return None
            if confirmation is None:
                raise DataRevisionError(
                    DataRevisionErrorCode.replan_required,
                    "the revision Run has no exact RevisionPlan confirmation",
                )
            plan = session.get(RevisionPlanModel, confirmation.revision_plan_id)
            if (
                plan is None
                or confirmation.run_id != run.id
                or confirmation.project_id != run.project_id
                or confirmation.owner_session_id != session_id
                or plan.project_id != run.project_id
                or plan.owner_session_id != session_id
                or run.parent_run_id != plan.parent_run_id
                or run.contract_id != plan.contract_id
                or run.request_hash != plan.plan_hash
            ):
                raise DataRevisionError(
                    DataRevisionErrorCode.replan_required,
                    "the revision Run and confirmed RevisionPlan binding drifted",
                )

            feedback_links = tuple(
                session.scalars(
                    select(RevisionPlanFeedbackModel)
                    .where(RevisionPlanFeedbackModel.revision_plan_id == plan.id)
                    .order_by(RevisionPlanFeedbackModel.position)
                )
            )
            decisions = tuple(
                session.scalars(
                    select(RevisionPlanVersionModel)
                    .where(RevisionPlanVersionModel.revision_plan_id == plan.id)
                    .order_by(RevisionPlanVersionModel.position)
                )
            )
            decision_payloads = tuple(_decision_payload(item) for item in decisions)
            expected_plan_hash = compute_revision_plan_hash(
                project_id=plan.project_id,
                parent_run_id=plan.parent_run_id,
                parent_run_revision=plan.parent_run_revision,
                contract_id=plan.contract_id,
                feedback_ids=tuple(item.feedback_id for item in feedback_links),
                recompute_steps=tuple(plan.recompute_steps),
                version_decisions=decision_payloads,
            )
            if plan.plan_hash != expected_plan_hash:
                raise DataRevisionError(
                    DataRevisionErrorCode.replan_required,
                    "the confirmed RevisionPlan hash no longer matches its frozen facts",
                )

            artifacts = tuple(
                session.scalars(
                    select(ResearchArtifactModel)
                    .where(
                        ResearchArtifactModel.id.in_(
                            item.artifact_id for item in decisions
                        )
                    )
                    .order_by(ResearchArtifactModel.id)
                    .with_for_update()
                )
            )
            artifact_by_id = {item.id: item for item in artifacts}
            if len(artifact_by_id) != len(decisions) or any(
                (artifact := artifact_by_id.get(item.artifact_id)) is None
                or artifact.project_id != plan.project_id
                or artifact.kind != item.artifact_kind
                or artifact.latest_version_id != item.artifact_version_id
                for item in decisions
            ):
                raise DataRevisionError(
                    DataRevisionErrorCode.baseline_stale,
                    "one or more frozen ArtifactVersion baselines are no longer latest",
                )

            data_decisions = {
                item.artifact_kind: item
                for item in decisions
                if item.artifact_kind in _DATA_KINDS
            }
            if not data_decisions:
                return RevisionRunContext(
                    artifacts={item.artifact_kind: item.artifact_id for item in decisions},
                    versions={
                        item.artifact_kind: item.artifact_version_id
                        for item in decisions
                    },
                    data_execution=None,
                )
            if set(data_decisions) != set(_DATA_KINDS):
                raise DataRevisionError(
                    DataRevisionErrorCode.replan_required,
                    "the confirmed plan does not freeze a complete data artifact bundle",
                )
            data_decision_values = {
                item.decision for item in data_decisions.values()
            }
            if data_decision_values == {"reuse"}:
                return RevisionRunContext(
                    artifacts={item.artifact_kind: item.artifact_id for item in decisions},
                    versions={
                        item.artifact_kind: item.artifact_version_id
                        for item in decisions
                    },
                    data_execution=None,
                )
            if data_decision_values != {"recompute"}:
                raise DataRevisionError(
                    DataRevisionErrorCode.replan_required,
                    "the confirmed plan splits one data artifact bundle across reuse and recompute",
                )
            version_rows = tuple(
                session.scalars(
                    select(ArtifactVersionModel).where(
                        ArtifactVersionModel.id.in_(
                            item.artifact_version_id
                            for item in data_decisions.values()
                        )
                    )
                )
            )
            version_by_id = {item.id: item for item in version_rows}
            if any(
                (version := version_by_id.get(item.artifact_version_id)) is None
                or version.project_id != plan.project_id
                or version.artifact_id != item.artifact_id
                or version.version_number != item.version_number
                for item in data_decisions.values()
            ):
                raise DataRevisionError(
                    DataRevisionErrorCode.replan_required,
                    "a frozen data ArtifactVersion no longer matches its plan decision",
                )

        reads: dict[str, Any] = {
            "dataset": self._reads.get_dataset(
                version_id=str(data_decisions["dataset"].artifact_version_id),
                session_id=session_id,
            ),
            "field_dictionary": self._reads.get_field_dictionary(
                version_id=str(
                    data_decisions["field_dictionary"].artifact_version_id
                ),
                session_id=session_id,
            ),
            "source_collection": self._reads.get_source_collection(
                version_id=str(
                    data_decisions["source_collection"].artifact_version_id
                ),
                session_id=session_id,
            ),
        }
        input_hashes = {item.input_hash for item in reads.values()}
        quality_hashes = {
            item.quality_projection.rule_set.content_hash for item in reads.values()
        }
        bundle_commitments = {
            item.quality_projection.bundle_commitment for item in reads.values()
        }
        if (
            len(input_hashes) != 1
            or len(quality_hashes) != 1
            or len(bundle_commitments) != 1
        ):
            raise DataRevisionError(
                DataRevisionErrorCode.input_not_replayable,
                "the frozen data ArtifactVersions do not share one build and quality closure",
            )
        input_hash = next(iter(input_hashes))
        try:
            baseline_input = self._build_inputs.get(
                project_id=plan.project_id,
                input_hash=input_hash,
            )
        except DataArtifactBuildInputReplayError as exc:
            raise DataRevisionError(
                DataRevisionErrorCode.input_not_replayable,
                "the frozen DataArtifactBuildInput cannot be replayed exactly",
            ) from exc

        result_payload: dict[str, Any] = {
            "schema_version": "3.0.0",
            "dataset": reads["dataset"].dataset,
            "field_dictionary": reads["field_dictionary"].field_dictionary,
            "source_collection": reads["source_collection"].source_collection,
            "input_hash": input_hash,
        }
        result_payload["output_hash"] = compute_data_artifact_output_hash(
            {
                **result_payload,
                "dataset": reads["dataset"].dataset.model_dump(mode="json"),
                "field_dictionary": reads[
                    "field_dictionary"
                ].field_dictionary.model_dump(mode="json"),
                "source_collection": reads[
                    "source_collection"
                ].source_collection.model_dump(mode="json"),
            }
        )
        baseline_result = DataArtifactBuildResult.model_validate(result_payload)
        baselines = tuple(
            DataRevisionArtifactBaseline(
                artifact_kind=kind,
                artifact_id=data_decisions[kind].artifact_id,
                baseline_version_id=data_decisions[kind].artifact_version_id,
                version_number=data_decisions[kind].version_number,
                decision=data_decisions[kind].decision,
                step_key=data_decisions[kind].step_key,
                candidate_content_hash=compute_data_artifact_public_payload_hash(
                    getattr(baseline_result, kind)
                ),
            )
            for kind in _DATA_KINDS
        )
        data_execution = DataRevisionExecutionInput(
            plan_hash=plan.plan_hash,
            baselines=baselines,
            baseline_input=baseline_input,
            baseline_result=baseline_result,
            baseline_quality_rule_set_content_hash=next(iter(quality_hashes)),
            current_mapping_rule_set=load_mapping_rule_set(),
            current_conversion_catalog=load_unit_conversion_catalog(),
            current_crossmatch_rule_set=load_crossmatch_rule_set(),
            current_alias_catalog=load_entity_alias_catalog(),
            current_source_policy=load_crossmatch_source_policy(),
            current_quality_rule_set_content_hash=(
                load_frozen_quality_rule_set().content_hash
            ),
            acquisition_recompute_authorized=(
                "fetching_data" in plan.recompute_steps
            ),
        )
        return RevisionRunContext(
            artifacts={item.artifact_kind: item.artifact_id for item in decisions},
            versions={
                item.artifact_kind: item.artifact_version_id for item in decisions
            },
            data_execution=data_execution,
        )


def _decision_payload(value: RevisionPlanVersionModel) -> dict[str, Any]:
    return {
        "artifact_version_id": str(value.artifact_version_id),
        "artifact_id": str(value.artifact_id),
        "artifact_kind": value.artifact_kind,
        "version_number": value.version_number,
        "decision": value.decision,
        "step_key": value.step_key,
    }


__all__ = ["DataRevisionContextLoader", "RevisionRunContext"]
