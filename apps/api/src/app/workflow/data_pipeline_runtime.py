"""Prepare the live cross-source data artifacts for a ResearchRun step.

This module is deliberately a deep execution seam.  It owns the data-pipeline
algorithm (source acquisition, crossmatch, mapping, and quality admission),
but it does not own RunStep transitions, leases, database writes, or producer
execution records.  The workflow worker can therefore call ``prepare`` inside
its existing attempt/lease boundary and hand the returned prepared artifacts
to its publisher.

The old worker contained this logic inline and mixed ``step_key`` with the
Run status when creating producer records.  ``DataPipelineRunInput.step_key``
is retained as an explicit identity value here; no attempt/status object is
accepted by this module, so the same category of mix-up cannot occur in the
data preparation seam.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, TypeAlias
from uuid import NAMESPACE_URL, UUID, uuid5

from app.schemas.core import ResearchContract
from app.schemas.crossmatch import (
    CrossmatchInput,
    CrossmatchResult,
    CrossmatchSourceInput,
    compute_crossmatch_input_hash,
    compute_crossmatch_source_input_hash,
)
from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    DataArtifactBuildResult,
    DatasetArtifactCandidate,
    FieldDictionaryArtifactCandidate,
    ManifestPins,
    SourceCollectionArtifactCandidate,
    compute_data_artifact_input_hash,
)
from app.schemas.data_quality import (
    DataQualityEvaluationInput,
    DataQualityEvaluationResult,
    compute_data_quality_input_hash,
)
from app.schemas.enums import SourceMode
from app.schemas.manifest import ManifestBundle
from app.schemas.source_acquisition import DataSourceDataLevel
from app.workflow.publisher import (
    AdmittedArtifactCandidate,
    ArtifactEvidenceBinding,
    ArtifactSourceSnapshotBinding,
    admit_artifact_candidate,
)
from services.data_pipeline.crossmatch import align_cross_source_records
from services.data_pipeline.crossmatch.policy import (
    load_crossmatch_rule_set,
    load_crossmatch_source_policy,
    load_entity_alias_catalog,
)
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.data_artifacts.admission import (
    validate_data_artifact_domain,
    validate_data_artifact_evidence,
)
from services.data_pipeline.data_artifacts.policy import (
    load_mapping_rule_set,
    load_unit_conversion_catalog,
)
from services.data_pipeline.data_quality import (
    admit_data_artifact_quality,
    build_data_quality_publication_validator,
    evaluate_data_quality,
)
from services.data_pipeline.data_quality.admission import QualityAdmittedDataArtifacts
from services.data_pipeline.data_quality.policy import load_frozen_quality_rule_set
from services.data_pipeline.query import normalize_toi_query
from services.data_pipeline.sources.nasa_exoplanet_archive import (
    NasaExoplanetArchiveAdapter,
)
from services.data_pipeline.sources.nasa_planetary_systems import (
    NasaPlanetarySystemsSupplementalAdapter,
)
from services.data_pipeline.sources.nasa_tap import NasaTapRequester
from services.data_pipeline.supplemental_query import normalize_ps_supplemental_query
from services.data_pipeline.sources.base import DataSourceAcquisitionResult


LOGGER = logging.getLogger(__name__)
_NAMESPACE = "https://xingwen.example/research-runtime"
_DISCOVERY_QUERY = (
    "select distinct top 20 t.tid from toi t join ps p on "
    "p.tic_id = CONCAT('TIC ',CAST(t.tid AS VARCHAR(20))) "
    "where t.tfopwg_disp='CP' and p.default_flag=1 "
    "and p.sy_dist <= 20 order by t.tid"
)


DataPipelineCandidate: TypeAlias = (
    DatasetArtifactCandidate
    | FieldDictionaryArtifactCandidate
    | SourceCollectionArtifactCandidate
)


class DataPipelineAcquisitionPort(Protocol):
    """Explicit boundary for source discovery and external acquisition."""

    def discover_nearby_confirmed_tic_ids(self) -> tuple[str, ...]:
        """Return the bounded, validated target list from the upstream service."""

    def acquire(
        self,
        *,
        manifests: ManifestBundle,
        tic_ids: tuple[str, ...],
    ) -> tuple[CrossmatchSourceInput, CrossmatchSourceInput]:
        """Acquire the two source inputs without crossmatching or mapping them."""


@dataclass(frozen=True, slots=True)
class DataPipelineRunInput:
    """Immutable inputs needed to prepare one data-pipeline step.

    ``acquisitions`` is an optional injection point for replay/unit tests and
    for a worker that already owns a source-acquisition activity.  When it is
    omitted, ``DataPipelineRuntime`` calls its explicit acquisition port.
    Neither this value object nor the runtime accepts a Session, lease, or
    attempt; persistence remains the publisher/worker responsibility.
    """

    project_id: UUID
    run_id: UUID
    step_key: str
    contract: ResearchContract
    acquisitions: tuple[CrossmatchSourceInput, CrossmatchSourceInput] | None = None

    def __post_init__(self) -> None:
        if not self.step_key.strip():
            raise ValueError("data pipeline step_key must not be empty")
        if str(self.contract.project_id) != str(self.project_id):
            raise ValueError(
                "ResearchContract is not owned by the Data Pipeline project"
            )


@dataclass(frozen=True, slots=True)
class DataPipelinePreparedArtifact:
    """One sealed candidate plus deterministic provenance bindings.

    The candidates are sealed by ``build_data_artifact_candidates`` and the
    full three-candidate bundle is quality-admitted before this result is
    returned.  The generic publisher currently exposes a final provenance
    bridge for the Dataset candidate; FieldDictionary and SourceCollection are
    retained here as part of the complete prepared bundle for the worker's
    domain-specific publisher bridge.
    """

    kind: str
    candidate: DataPipelineCandidate
    source_snapshot_bindings: tuple[ArtifactSourceSnapshotBinding, ...]
    evidence_bindings: tuple[ArtifactEvidenceBinding, ...]


@dataclass(frozen=True, slots=True)
class DataPipelinePreparedResult:
    """Complete deterministic output of the data preparation seam."""

    project_id: UUID
    run_id: UUID
    step_key: str
    acquisitions: tuple[CrossmatchSourceInput, CrossmatchSourceInput]
    crossmatch_input: CrossmatchInput
    data_input: DataArtifactBuildInput
    build_result: DataArtifactBuildResult
    quality: QualityAdmittedDataArtifacts
    artifacts: tuple[DataPipelinePreparedArtifact, ...]

    @property
    def quality_result(self) -> DataQualityEvaluationResult:
        """Expose the trusted quality result without reopening its bundle."""

        return self.quality.evaluation_result

    @property
    def dataset(self) -> DatasetArtifactCandidate:
        return self.build_result.dataset

    @property
    def field_dictionary(self) -> FieldDictionaryArtifactCandidate:
        return self.build_result.field_dictionary

    @property
    def source_collection(self) -> SourceCollectionArtifactCandidate:
        return self.build_result.source_collection


@dataclass(frozen=True, slots=True)
class NasaLiveDataAcquisition:
    """The only production implementation that performs NASA network calls."""

    manifests: ManifestBundle
    page_delay_seconds: float = 0.0
    toi_adapter_factory: Callable[..., NasaExoplanetArchiveAdapter] = (
        NasaExoplanetArchiveAdapter
    )
    ps_adapter_factory: Callable[..., NasaPlanetarySystemsSupplementalAdapter] = (
        NasaPlanetarySystemsSupplementalAdapter
    )
    requester_factory: Callable[..., NasaTapRequester] = NasaTapRequester

    def discover_nearby_confirmed_tic_ids(self) -> tuple[str, ...]:
        """Call NASA TAP once and fail closed on malformed/duplicate IDs."""

        response, _, _ = self.requester_factory(
            failure_prefix="NASA_TARGET_DISCOVERY",
            source_label="nasa-nearby-confirmed-hosts",
            logger=LOGGER,
        ).request({"query": _DISCOVERY_QUERY, "format": "json"})
        try:
            payload = json.loads(response.body.decode("utf-8"))
            tic_ids = tuple(
                str(item["tid"])
                for item in payload
                if isinstance(item, dict) and isinstance(item.get("tid"), int)
            )
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
            raise ValueError("NASA 目标发现结果无法验证") from error
        return _require_unique_tic_ids(tic_ids)

    def acquire(
        self,
        *,
        manifests: ManifestBundle,
        tic_ids: tuple[str, ...],
    ) -> tuple[CrossmatchSourceInput, CrossmatchSourceInput]:
        """Acquire TOI and PS data; no cross-source interpretation occurs here."""

        mode = SourceMode.live
        level = DataSourceDataLevel.live_result
        left_result = self.toi_adapter_factory(
            page_delay_seconds=self.page_delay_seconds
        ).acquire(
            normalize_toi_query(
                manifests,
                page_size=100,
                max_pages=1,
                record_limit=100,
                tic_ids=tic_ids,
                confirmed_only=True,
            ),
            source_mode=mode,
            data_level=level,
        )
        right_result = self.ps_adapter_factory(
            page_delay_seconds=self.page_delay_seconds
        ).acquire(
            normalize_ps_supplemental_query(
                manifests,
                tic_ids=tic_ids,
                page_size=100,
                max_pages=1,
                record_limit=100,
                default_only=True,
                max_distance_parsecs=20,
            ),
            source_mode=mode,
            data_level=level,
        )
        return (
            _to_crossmatch_source_input(left_result, mode=mode, level=level),
            _to_crossmatch_source_input(right_result, mode=mode, level=level),
        )


class DataPipelineRuntime:
    """Execute source-to-quality preparation without touching Workflow state."""

    def __init__(
        self,
        manifests: ManifestBundle,
        *,
        acquisition: DataPipelineAcquisitionPort | None = None,
    ) -> None:
        self._manifests = manifests
        self._acquisition = acquisition or NasaLiveDataAcquisition(manifests)

    def acquire_live_data(
        self,
    ) -> tuple[CrossmatchSourceInput, CrossmatchSourceInput]:
        """Discover targets and acquire bounded live source inputs."""

        tic_ids = _require_unique_tic_ids(
            self._acquisition.discover_nearby_confirmed_tic_ids()
        )
        acquisitions = self._acquisition.acquire(
            manifests=self._manifests,
            tic_ids=tic_ids,
        )
        return _validate_acquisitions(acquisitions)

    def prepare(self, request: DataPipelineRunInput) -> DataPipelinePreparedResult:
        """Build, quality-admit, and seal the complete three-artifact bundle."""

        if request.contract.project_id != str(request.project_id):
            raise ValueError("ResearchContract project ownership changed")
        acquisitions = _validate_acquisitions(
            request.acquisitions
            if request.acquisitions is not None
            else self.acquire_live_data()
        )
        left, right = acquisitions
        crossmatch_input = _build_crossmatch_input(
            self._manifests, left=left, right=right
        )
        crossmatch = align_cross_source_records(crossmatch_input)
        data_input = _build_data_input(
            manifests=self._manifests,
            contract=request.contract,
            acquisitions=acquisitions,
            crossmatch_input=crossmatch,
        )
        build_result = build_data_artifact_candidates(data_input)
        quality_input = _build_quality_input(
            contract=request.contract,
            data_input=data_input,
            build_result=build_result,
        )
        quality_result = evaluate_data_quality(quality_input)
        if not isinstance(quality_result, DataQualityEvaluationResult):
            raise ValueError("实时数据未通过研究协议的数据质量约束")
        quality = admit_data_artifact_quality(
            build_result=build_result,
            evaluation_input=quality_input,
            evaluation_result=quality_result,
        )
        artifacts = tuple(
            DataPipelinePreparedArtifact(
                kind=kind,
                candidate=candidate,
                source_snapshot_bindings=_source_snapshot_bindings(
                    request.project_id, candidate.source_snapshot_ids
                ),
                evidence_bindings=_data_evidence_bindings(
                    request.run_id,
                    kind=kind,
                    candidate=build_result.dataset,
                    project_id=request.project_id,
                ),
            )
            for kind, candidate in (
                ("dataset", build_result.dataset),
                ("field_dictionary", build_result.field_dictionary),
                ("source_collection", build_result.source_collection),
            )
        )
        return DataPipelinePreparedResult(
            project_id=request.project_id,
            run_id=request.run_id,
            step_key=request.step_key,
            acquisitions=acquisitions,
            crossmatch_input=crossmatch_input,
            data_input=data_input,
            build_result=build_result,
            quality=quality,
            artifacts=artifacts,
        )

    def admit_dataset(
        self,
        prepared: DataPipelinePreparedResult,
    ) -> AdmittedArtifactCandidate:
        """Return the generic Publisher-ready Dataset admission.

        The generic Publisher's data provenance bridge currently accepts the
        Dataset candidate.  The other two sealed candidates remain available
        on ``prepared.artifacts`` for the dedicated three-artifact bridge.
        """

        artifact = next(item for item in prepared.artifacts if item.kind == "dataset")
        quality_validator = build_data_quality_publication_validator(
            prepared.quality,
            candidate_kind="dataset",
        )
        return admit_artifact_candidate(
            artifact.candidate,
            schema_version=artifact.candidate.schema_version,
            source_snapshot_ids=artifact.candidate.source_snapshot_ids,
            evidence_ids=artifact.candidate.evidence_ids,
            evidence_validator=validate_data_artifact_evidence,
            domain_validator=validate_data_artifact_domain,
            quality_validator=quality_validator,
            source_snapshot_bindings=artifact.source_snapshot_bindings,
            evidence_bindings=artifact.evidence_bindings,
        )


def _to_crossmatch_source_input(
    result: DataSourceAcquisitionResult,
    *,
    mode: SourceMode,
    level: DataSourceDataLevel,
) -> CrossmatchSourceInput:
    return CrossmatchSourceInput(
        source_mode=mode,
        data_level=level,
        records=result.records,
        snapshot=result.snapshot,
        completion=result.completion,
    )


def _require_unique_tic_ids(values: Sequence[str | int]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if isinstance(value, bool) or not text.isdigit() or int(text) < 1:
            raise ValueError("NASA 目标发现未返回唯一的有效 TIC 标识")
        normalized.append(str(int(text)))
    if not normalized or len(normalized) > 100:
        raise ValueError("NASA 目标发现未返回唯一的有效 TIC 标识")
    if len(normalized) != len(set(normalized)):
        raise ValueError("NASA 目标发现未返回唯一的有效 TIC 标识")
    return tuple(normalized)


def _validate_acquisitions(
    acquisitions: tuple[CrossmatchSourceInput, CrossmatchSourceInput],
) -> tuple[CrossmatchSourceInput, CrossmatchSourceInput]:
    if len(acquisitions) != 2:
        raise ValueError("Data Pipeline requires exactly two source acquisitions")
    left, right = acquisitions
    if left.snapshot.source_id == right.snapshot.source_id:
        raise ValueError("Data Pipeline requires two independent source acquisitions")
    return acquisitions


def _build_crossmatch_input(
    manifests: ManifestBundle,
    *,
    left: CrossmatchSourceInput,
    right: CrossmatchSourceInput,
) -> CrossmatchInput:
    rules = load_crossmatch_rule_set()
    payload: dict[str, Any] = {
        "case_manifest_id": manifests.case_manifest.case_id,
        "case_manifest_version": manifests.case_manifest.manifest_version,
        "case_manifest_content_hash": manifests.case_manifest.content_hash,
        "field_manifest_id": manifests.field_manifest.manifest_id,
        "field_manifest_version": manifests.field_manifest.manifest_version,
        "field_manifest_content_hash": manifests.field_manifest.content_hash,
        "rule_set": rules.model_dump(mode="json"),
        "alias_catalog": load_entity_alias_catalog().model_dump(mode="json"),
        "source_policy": load_crossmatch_source_policy().model_dump(mode="json"),
        "left": left.model_dump(mode="json"),
        "right": right.model_dump(mode="json"),
        "manual_review_decisions": (),
    }
    payload["source_input_hash"] = compute_crossmatch_source_input_hash(payload)
    payload["input_hash"] = compute_crossmatch_input_hash(payload)
    return CrossmatchInput.model_validate(payload)


def _build_data_input(
    *,
    manifests: ManifestBundle,
    contract: ResearchContract,
    acquisitions: tuple[CrossmatchSourceInput, CrossmatchSourceInput],
    crossmatch_input: CrossmatchResult,
) -> DataArtifactBuildInput:
    mapping = load_mapping_rule_set()
    conversion = load_unit_conversion_catalog()
    pins = ManifestPins(
        case_manifest_id=manifests.case_manifest.case_id,
        case_manifest_version=manifests.case_manifest.manifest_version,
        case_manifest_content_hash=manifests.case_manifest.content_hash,
        field_manifest_id=manifests.field_manifest.manifest_id,
        field_manifest_version=manifests.field_manifest.manifest_version,
        field_manifest_content_hash=manifests.field_manifest.content_hash,
    )
    payload: dict[str, Any] = {
        "manifest_pins": pins,
        "requested_fields": contract.requested_fields,
        "left_acquisition": acquisitions[0],
        "right_acquisition": acquisitions[1],
        "crossmatch_result": crossmatch_input,
        "mapping_rule_set": mapping,
        "conversion_catalog": conversion,
        "producer_version": mapping.producer_version,
        "quality_constraints_reference": "research_contract.quality_constraints",
    }
    unhashed = DataArtifactBuildInput.model_construct(
        **payload,
        input_hash="sha256:" + "0" * 64,
    )
    payload["input_hash"] = compute_data_artifact_input_hash(unhashed)
    return DataArtifactBuildInput.model_validate(payload)


def _build_quality_input(
    *,
    contract: ResearchContract,
    data_input: DataArtifactBuildInput,
    build_result: DataArtifactBuildResult,
) -> DataQualityEvaluationInput:
    payload: dict[str, Any] = {
        "data_artifact_input": data_input,
        "dataset_candidate": build_result.dataset,
        "field_dictionary_candidate": build_result.field_dictionary,
        "source_collection_candidate": build_result.source_collection,
        "research_contract": contract,
        "quality_rule_set": load_frozen_quality_rule_set(),
    }
    unhashed = DataQualityEvaluationInput.model_construct(
        **payload,
        input_hash="sha256:" + "0" * 64,
    )
    payload["input_hash"] = compute_data_quality_input_hash(unhashed)
    return DataQualityEvaluationInput.model_validate(payload)


def _source_snapshot_bindings(
    project_id: UUID,
    pipeline_ids: Sequence[str],
) -> tuple[ArtifactSourceSnapshotBinding, ...]:
    return tuple(
        ArtifactSourceSnapshotBinding(
            pipeline_source_snapshot_id=pipeline_id,
            persisted_source_snapshot_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"{_NAMESPACE}/{project_id}/source-snapshot/{pipeline_id}",
                )
            ),
        )
        for pipeline_id in pipeline_ids
    )


def _data_evidence_bindings(
    run_id: UUID,
    *,
    kind: str,
    candidate: DatasetArtifactCandidate,
    project_id: UUID,
) -> tuple[ArtifactEvidenceBinding, ...]:
    snapshots = {
        item.pipeline_source_snapshot_id: item.persisted_source_snapshot_id
        for item in _source_snapshot_bindings(project_id, candidate.source_snapshot_ids)
    }
    transformations = {
        item.evidence_id: item for item in candidate.transformation_evidence
    }
    crossmatch = {item.evidence_id: item for item in candidate.crossmatch_evidence}
    bindings: list[ArtifactEvidenceBinding] = []
    for pipeline_id in candidate.evidence_ids:
        transformation = transformations.get(pipeline_id)
        if transformation is not None:
            target_type = "canonical_field"
            target_id = transformation.canonical_field_id
            pipeline_snapshot_id = transformation.locator.source_snapshot_id
        else:
            evidence = crossmatch.get(pipeline_id)
            if evidence is None:
                raise ValueError(
                    "Data Artifact Evidence registry is not materializable"
                )
            left_snapshot_ids = {
                item.source_snapshot_id for item in evidence.left_locators
            }
            if len(left_snapshot_ids) != 1:
                raise ValueError("Crossmatch Evidence requires one left SourceSnapshot")
            target_type = "crossmatch"
            target_id = pipeline_id
            pipeline_snapshot_id = next(iter(left_snapshot_ids))
        persisted_snapshot_id = snapshots.get(pipeline_snapshot_id)
        if persisted_snapshot_id is None:
            raise ValueError(
                "Data Artifact Evidence references an unknown SourceSnapshot"
            )
        bindings.append(
            ArtifactEvidenceBinding(
                target_type=target_type,
                target_id=target_id,
                pipeline_evidence_id=pipeline_id,
                pipeline_source_snapshot_id=pipeline_snapshot_id,
                persisted_evidence_id=str(
                    uuid5(
                        NAMESPACE_URL,
                        f"{_NAMESPACE}/{run_id}/{kind}/data-evidence/{pipeline_id}",
                    )
                ),
                persisted_source_snapshot_id=persisted_snapshot_id,
            )
        )
    return tuple(bindings)


__all__ = [
    "DataPipelineAcquisitionPort",
    "DataPipelineCandidate",
    "DataPipelinePreparedArtifact",
    "DataPipelinePreparedResult",
    "DataPipelineRunInput",
    "DataPipelineRuntime",
    "NasaLiveDataAcquisition",
]
