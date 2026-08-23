"""Task-owned scientific RunStep execution within the current Workflow."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RunStepModel, SourceSnapshotModel
from app.schemas.core import ArtifactKind, ScientificSkillId
from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    SourceTableDataArtifactAuthority,
    compute_data_artifact_input_hash,
)
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.scientific_capabilities import capability_for
from app.services.content_storage import ContentStorage
from app.workflow.data_artifact_publication import (
    DataArtifactPublicationConfig,
    DataArtifactPublicationService,
)
from app.workflow.scientific_admission import ScientificStepAdmission
from app.workflow.scientific_inputs import DatabaseScientificInputResolver
from app.workflow.scientific_provenance import (
    DatabaseGaiaTapResponseCache,
    DatabaseScientificSourceRecorder,
)
from app.workflow.publisher import ArtifactPublication
from app.workflow.step_publication import (
    PreparedStep,
    RunStepContext,
    StepPublicationFactory,
)
from app.workflow.store import AttemptHandle, LeaseGrant
from services.data_pipeline.data_artifacts.policy import (
    load_mapping_rule_set,
    load_unit_conversion_catalog,
)
from services.scientific_skills.execution import (
    ScientificStepAdapter,
    ScientificStepOutput,
)
from services.scientific_skills.astro_acquisition import GaiaTapAdapter
from services.scientific_skills.registry import (
    ScientificSkillRegistry,
    build_scientific_skill_registry,
)


class ScientificStepService:
    """Execute one task-owned scientific step through the bounded skill seam."""

    def __init__(
        self,
        *,
        factory: Callable[[], Session],
        content_storage: ContentStorage,
        publications: StepPublicationFactory,
        registry: ScientificSkillRegistry | None = None,
    ) -> None:
        self._factory = factory
        self._content_storage = content_storage
        self._publications = publications
        self._registry = registry or build_scientific_skill_registry(
            gaia_handler=GaiaTapAdapter(
                cache=DatabaseGaiaTapResponseCache(factory)
            ).acquire
        )
        self._admission = ScientificStepAdmission(factory)
        self._data_artifacts = DataArtifactPublicationService(publications)

    def execute(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> PreparedStep:
        task_id, skill_id = self._step_binding(attempt.run_step_id)
        resolver = DatabaseScientificInputResolver(
            self._factory,
            self._content_storage,
            project_id=str(context.project_id),
        )
        recorder = DatabaseScientificSourceRecorder(self._factory)
        adapter = ScientificStepAdapter(
            registry=self._registry,
            content_storage=self._content_storage,
            source_recorder=recorder,
        )
        output = asyncio.run(
            adapter.execute(
                task_id=task_id,
                project_id=str(context.project_id),
                run_id=str(context.run_id),
                contract=context.contract,
                resolve_inputs=resolver.resolve,
            )
        )
        publications = self._admission.prepare_publications(
            attempt=attempt,
            lease=lease,
            step_key=step_key,
            contract=context.contract,
            output=output,
            source_mode=output.source_mode,
        )
        data_publications = self._prepare_gaia_data_publications(
            context,
            step_key=step_key,
            attempt=attempt,
            lease=lease,
            output=output,
        )
        capability = capability_for(skill_id)
        all_publications = (*publications, *data_publications)
        summary = f"{capability['label']}已完成，产出 {len(all_publications)} 个结果版本"
        return PreparedStep(
            publications=all_publications,
            activity_result_summary=summary,
        )

    def _prepare_gaia_data_publications(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
        output: ScientificStepOutput,
    ) -> tuple[ArtifactPublication, ...]:
        data_kinds = (
            ArtifactKind.dataset,
            ArtifactKind.field_dictionary,
            ArtifactKind.source_collection,
        )
        requested_kinds = {
            kind for kind in context.contract.output_requirements
        }
        if (
            output.skill_id is not ScientificSkillId.gaia_cone_search
            or not output.source_table_admissions
            or not requested_kinds.intersection(data_kinds)
        ):
            return ()
        if len(output.source_table_admissions) != 1:
            raise ValueError("Gaia Data Artifact requires exactly one SourceTableAdmission")
        admission = output.source_table_admissions[0]
        if admission.source_snapshot_id not in output.source_snapshot_ids:
            raise ValueError("Gaia SourceTableAdmission snapshot is not in the skill output")
        snapshot = self._source_snapshot(
            project_id=context.project_id,
            snapshot_id=admission.source_snapshot_id,
        )
        mapping = load_mapping_rule_set()
        conversion = load_unit_conversion_catalog()
        data_payload = {
            "manifest_pins": admission.manifest_pins,
            "requested_fields": context.contract.requested_fields,
            "authority": SourceTableDataArtifactAuthority(
                source_snapshot=snapshot,
                source_table_admission=admission,
            ),
            "mapping_rule_set": mapping,
            "conversion_catalog": conversion,
            "producer_version": mapping.producer_version,
            "quality_constraints_reference": "research_contract.quality_constraints",
        }
        unhashed = DataArtifactBuildInput.model_construct(
            **data_payload,
            input_hash="sha256:" + "0" * 64,
        )
        data_payload["input_hash"] = compute_data_artifact_input_hash(unhashed)
        data_input = DataArtifactBuildInput.model_validate(data_payload)
        publication_config = DataArtifactPublicationConfig(
            publish_kinds=tuple(kind for kind in data_kinds if kind in requested_kinds),
            operation_key_prefix="gaia_data_artifact",
            producer_error_code="GAIA_DATA_ARTIFACT_BUILD_FAILED",
            producer_version=mapping.producer_version,
            quality_failure_message="Gaia SourceTable did not pass Data Quality",
            source_mode=output.source_mode,
        )
        prepared = self._data_artifacts.prepare(
            context,
            step_key=step_key,
            attempt=attempt,
            lease=lease,
            data_input=data_input,
            config=publication_config,
        )
        return self._data_artifacts.publish(
            context,
            prepared=prepared,
            config=publication_config,
        )

    def _source_snapshot(
        self,
        *,
        project_id: UUID,
        snapshot_id: str,
    ) -> SourceSnapshotRecord:
        try:
            snapshot_uuid = UUID(str(snapshot_id))
        except ValueError as exc:
            raise ValueError("Gaia SourceSnapshot identity is not a UUID") from exc
        with self._factory() as session:
            row = session.scalar(
                select(SourceSnapshotModel).where(
                    SourceSnapshotModel.id == snapshot_uuid,
                    SourceSnapshotModel.project_id == project_id,
                )
            )
        if row is None:
            raise ValueError("Gaia SourceSnapshot was not persisted for this project")
        return SourceSnapshotRecord(
            snapshot_id=str(row.id),
            source_id=row.source_id,
            source_type=row.source_type,
            retrieved_at=row.retrieved_at,
            query=json.dumps(
                row.query,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            query_hash=row.query_hash,
            source_version_or_etag=row.source_version_or_etag,
            content_hash=row.content_hash,
            license_note=row.license_note,
            cache_version=row.cache_version,
            request_metadata=dict(row.request_metadata),
        )

    def _step_binding(self, run_step_id: object) -> tuple[str, str]:
        with self._factory() as session:
            step = session.get(RunStepModel, run_step_id)
        if step is None or step.task_id is None or step.skill_id is None:
            raise ValueError("scientific RunStep is missing its task binding")
        return step.task_id, step.skill_id
