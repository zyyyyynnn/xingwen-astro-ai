"""Process-local Data Quality Evaluation admission bound to the exact Data Artifact sealed candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.data_artifacts import (
    DataArtifactBuildResult,
    DatasetArtifactCandidate,
    FieldDictionaryArtifactCandidate,
    SourceCollectionArtifactCandidate,
    compute_data_artifact_public_payload_hash,
)
from app.schemas.data_quality import (
    DataQualityEvaluationInput,
    DataQualityEvaluationResult,
    DataQualityProjection,
    QualityErrorCode,
    QualityFailureStage,
    QualityArtifactReference,
    compute_data_quality_result_id,
)
from app.workflow.publisher import AdmissionValidator, _seal_data_quality_attestation

from .errors import DataQualityError
from .evaluator import evaluate_data_quality
from .policy import require_frozen_quality_rule_set


Candidate = DatasetArtifactCandidate | FieldDictionaryArtifactCandidate | SourceCollectionArtifactCandidate
CandidateKind = Literal["dataset", "field_dictionary", "source_collection"]


class _AdmissionContext(Protocol):
    candidate: Candidate
    source_snapshot_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class DataQualityAdmissionSnapshot:
    input_json: str
    input_hash: str
    result_id: str
    result_input_hash: str
    result_output_hash: str
    result_content_hash: str
    plan_content_hash: str
    evaluation_commitment: str
    contract_id: str
    contract_version: int
    contract_content_hash: str
    rule_set_id: str
    rule_set_version: str
    rule_set_content_hash: str
    candidate_ids: tuple[str, ...]
    candidate_input_hashes: tuple[str, ...]
    candidate_output_hashes: tuple[str, ...]
    dataset_canonical_content_hash: str
    dataset_lineage_hash: str
    source_snapshot_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    original_candidate_object_ids: tuple[int, ...]
    bundle_commitment: str


@dataclass(frozen=True)
class QualityAdmittedDataArtifacts:
    build_result: DataArtifactBuildResult
    evaluation_input: DataQualityEvaluationInput
    evaluation_result: DataQualityEvaluationResult
    snapshot: DataQualityAdmissionSnapshot


def admit_data_artifact_quality(
    *,
    build_result: DataArtifactBuildResult,
    evaluation_input: DataQualityEvaluationInput,
    evaluation_result: DataQualityEvaluationResult,
) -> QualityAdmittedDataArtifacts:
    """Create a process-local admission only for a passing, exact Data Artifact bundle."""

    candidates = (
        build_result.dataset,
        build_result.field_dictionary,
        build_result.source_collection,
    )
    input_candidates = (
        evaluation_input.dataset_candidate,
        evaluation_input.field_dictionary_candidate,
        evaluation_input.source_collection_candidate,
    )
    if any(left is not right for left, right in zip(candidates, input_candidates, strict=True)):
        raise DataQualityError(
            QualityErrorCode.QUALITY_DATA_ARTIFACT_CANDIDATE_MISMATCH,
            "quality input is not bound to the original Data Artifact candidate instances",
            stage=QualityFailureStage.admission_validation,
        )
    try:
        if any(not candidate.__artifact_publication_is_admitted__() for candidate in candidates):
            raise ValueError("one or more Data Artifact candidates are not sealed")
        DataArtifactBuildResult.model_validate_json(build_result.model_dump_json())
        reparsed_input = DataQualityEvaluationInput.model_validate_json(
            evaluation_input.model_dump_json()
        )
        if not isinstance(evaluation_result, DataQualityEvaluationResult):
            raise ValueError("only a typed Data Quality Evaluation result can be admitted")
        reparsed_result = DataQualityEvaluationResult.model_validate_json(
            evaluation_result.model_dump_json()
        )
    except (ValidationError, ValueError, AttributeError) as error:
        raise DataQualityError(
            QualityErrorCode.QUALITY_ADMISSION_NOT_SEALED,
            "quality admission failed immutable input or Data Artifact seal validation",
            stage=QualityFailureStage.admission_validation,
            cause=error,
        ) from error
    if reparsed_input != evaluation_input or reparsed_result != evaluation_result:
        raise DataQualityError(
            QualityErrorCode.QUALITY_RESULT_HASH_MISMATCH,
            "quality admission input or result changed during revalidation",
            stage=QualityFailureStage.admission_validation,
        )
    try:
        require_frozen_quality_rule_set(reparsed_input.quality_rule_set)
    except Exception as error:
        raise DataQualityError(
            QualityErrorCode.QUALITY_RULE_SET_MISMATCH,
            "quality admission RuleSet is not the frozen repository RuleSet",
            stage=QualityFailureStage.admission_validation,
            cause=error,
        ) from error
    canonical_result = evaluate_data_quality(reparsed_input)
    if not isinstance(canonical_result, DataQualityEvaluationResult):
        raise DataQualityError(
            QualityErrorCode.QUALITY_RESULT_HASH_MISMATCH,
            "quality admission input does not produce a typed Data Quality Evaluation result",
            stage=QualityFailureStage.admission_validation,
        )
    if canonical_result != reparsed_result:
        raise DataQualityError(
            QualityErrorCode.QUALITY_RESULT_HASH_MISMATCH,
            "quality admission result is not the canonical evaluator output",
            stage=QualityFailureStage.admission_validation,
        )
    trusted_result = canonical_result
    if trusted_result.contract_gate.overall_status.value != "pass":
        code = (
            QualityErrorCode.QUALITY_CONSTRAINT_FAILED
            if trusted_result.contract_gate.overall_status.value == "fail"
            else QualityErrorCode.QUALITY_CONSTRAINT_INSUFFICIENT
        )
        raise DataQualityError(
            code,
            "only a passing ResearchContract quality gate can be admitted",
            stage=QualityFailureStage.admission_validation,
        )
    if trusted_result.input_hash != reparsed_input.input_hash:
        raise DataQualityError(
            QualityErrorCode.QUALITY_RESULT_HASH_MISMATCH,
            "quality result input_hash differs from quality input",
            stage=QualityFailureStage.admission_validation,
        )
    expected_candidate_references = (
        QualityArtifactReference(
            kind="dataset",
            candidate_id=build_result.dataset.candidate_id,
            input_hash=build_result.dataset.input_hash,
            output_hash=build_result.dataset.output_hash,
            canonical_content_hash=build_result.dataset.canonical_content_hash,
            lineage_hash=build_result.dataset.lineage_hash,
        ),
        QualityArtifactReference(
            kind="field_dictionary",
            candidate_id=build_result.field_dictionary.candidate_id,
            input_hash=build_result.field_dictionary.input_hash,
            output_hash=build_result.field_dictionary.output_hash,
        ),
        QualityArtifactReference(
            kind="source_collection",
            candidate_id=build_result.source_collection.candidate_id,
            input_hash=build_result.source_collection.input_hash,
            output_hash=build_result.source_collection.output_hash,
        ),
    )
    references = trusted_result.input_references
    if (
        references.data_artifact_input_hash != evaluation_input.data_artifact_input.input_hash
        or references.candidates != expected_candidate_references
        or references.crossmatch_result_id
        != evaluation_input.data_artifact_input.crossmatch_result.result_id
        or references.crossmatch_input_hash
        != evaluation_input.data_artifact_input.crossmatch_result.input_hash
        or references.crossmatch_output_hash
        != evaluation_input.data_artifact_input.crossmatch_result.output_hash
        or references.crossmatch_content_hash
        != evaluation_input.data_artifact_input.crossmatch_result.content_hash
        or references.research_contract_id != evaluation_input.research_contract.id
        or references.research_contract_version != evaluation_input.research_contract.version
        or references.research_contract_content_hash
        != evaluation_input.research_contract.content_hash
        or references.quality_rule_set_id != evaluation_input.quality_rule_set.rule_set_id
        or references.quality_rule_set_version != evaluation_input.quality_rule_set.version
        or references.quality_rule_set_content_hash
        != evaluation_input.quality_rule_set.content_hash
        or trusted_result.result_id
        != compute_data_quality_result_id(
            evaluation_input.input_hash,
            evaluation_input.quality_rule_set.content_hash,
        )
        or trusted_result.source_snapshot_ids != build_result.dataset.source_snapshot_ids
        or trusted_result.evidence_ids != build_result.dataset.evidence_ids
    ):
        raise DataQualityError(
            QualityErrorCode.QUALITY_RESULT_HASH_MISMATCH,
            "quality result references do not match the exact Data Artifact/Data Quality Evaluation input",
            stage=QualityFailureStage.admission_validation,
        )
    snapshot = _make_snapshot(build_result, reparsed_input, trusted_result)
    return QualityAdmittedDataArtifacts(
        build_result=build_result,
        evaluation_input=reparsed_input,
        evaluation_result=trusted_result,
        snapshot=snapshot,
    )


def build_data_quality_publication_validator(
    admitted: QualityAdmittedDataArtifacts,
    *,
    candidate_kind: CandidateKind,
) -> AdmissionValidator:
    """Return the Data Quality Evaluation validator accepted by the Publisher port."""

    expected = {
        "dataset": admitted.build_result.dataset,
        "field_dictionary": admitted.build_result.field_dictionary,
        "source_collection": admitted.build_result.source_collection,
    }[candidate_kind]

    def validate(context: _AdmissionContext) -> None:
        candidate = context.candidate
        if candidate is not expected or id(candidate) not in admitted.snapshot.original_candidate_object_ids:
            raise DataQualityError(
                QualityErrorCode.QUALITY_DATA_ARTIFACT_CANDIDATE_MISMATCH,
                "Publisher candidate is not the exact admitted Data Artifact instance",
                stage=QualityFailureStage.admission_validation,
            )
        try:
            if not candidate.__artifact_publication_is_admitted__():
                raise ValueError("Data Artifact candidate seal is no longer valid")
        except (AttributeError, ValueError) as error:
            raise DataQualityError(
                QualityErrorCode.QUALITY_ADMISSION_NOT_SEALED,
                "Data Artifact candidate publication seal is invalid",
                stage=QualityFailureStage.admission_validation,
                cause=error,
            ) from error
        if tuple(context.source_snapshot_ids) != admitted.snapshot.source_snapshot_ids:
            raise DataQualityError(
                QualityErrorCode.QUALITY_METRIC_REFERENCE_INVALID,
                "Publisher SourceSnapshot references differ from Data Quality Evaluation admission",
                stage=QualityFailureStage.admission_validation,
            )
        if tuple(context.evidence_ids) != admitted.snapshot.evidence_ids:
            raise DataQualityError(
                QualityErrorCode.QUALITY_METRIC_REFERENCE_INVALID,
                "Publisher Evidence references differ from Data Quality Evaluation admission",
                stage=QualityFailureStage.admission_validation,
            )
        try:
            immutable_input = DataQualityEvaluationInput.model_validate_json(
                admitted.snapshot.input_json
            )
        except ValidationError as error:
            raise DataQualityError(
                QualityErrorCode.QUALITY_INPUT_INVALID,
                "immutable Data Quality Evaluation input snapshot is invalid",
                stage=QualityFailureStage.admission_validation,
                cause=error,
            ) from error
        candidate_index = {
            "dataset": 0,
            "field_dictionary": 1,
            "source_collection": 2,
        }[candidate_kind]
        if (
            candidate.candidate_id != admitted.snapshot.candidate_ids[candidate_index]
            or candidate.input_hash != admitted.snapshot.candidate_input_hashes[candidate_index]
            or candidate.output_hash != admitted.snapshot.candidate_output_hashes[candidate_index]
        ):
            raise DataQualityError(
                QualityErrorCode.QUALITY_DATA_ARTIFACT_CANDIDATE_MISMATCH,
                "candidate payload differs from Data Quality Evaluation admission candidate binding",
                stage=QualityFailureStage.admission_validation,
            )
        if (
            admitted.snapshot.result_id != admitted.evaluation_result.result_id
            or admitted.snapshot.result_input_hash != admitted.evaluation_result.input_hash
            or admitted.snapshot.result_output_hash != admitted.evaluation_result.output_hash
            or admitted.snapshot.result_content_hash != admitted.evaluation_result.content_hash
            or admitted.snapshot.plan_content_hash
            != admitted.evaluation_result.evaluation_plan.content_hash
        ):
            raise DataQualityError(
                QualityErrorCode.QUALITY_RESULT_HASH_MISMATCH,
                "Data Quality Evaluation result fields differ from the admission commitment",
                stage=QualityFailureStage.admission_validation,
            )
        if immutable_input != admitted.evaluation_input:
            raise DataQualityError(
                QualityErrorCode.QUALITY_RESULT_HASH_MISMATCH,
                "immutable Data Quality Evaluation input differs from the admission commitment",
                stage=QualityFailureStage.admission_validation,
            )
        if admitted.snapshot.evaluation_commitment != _evaluation_commitment(
            admitted.evaluation_input,
            admitted.evaluation_result,
        ):
            raise DataQualityError(
                QualityErrorCode.QUALITY_RESULT_HASH_MISMATCH,
                "Data-quality evaluation commitment is not self-consistent",
                stage=QualityFailureStage.admission_validation,
            )
        if admitted.snapshot.bundle_commitment != _bundle_commitment(admitted.snapshot):
            raise DataQualityError(
                QualityErrorCode.QUALITY_RESULT_HASH_MISMATCH,
                "Data Artifact/Data Quality Evaluation bundle commitment is not self-consistent",
                stage=QualityFailureStage.admission_validation,
            )
        if admitted.evaluation_result.contract_gate.overall_status.value != "pass":
            raise DataQualityError(
                QualityErrorCode.QUALITY_CONSTRAINT_FAILED,
                "Publisher quality gate is not passing",
                stage=QualityFailureStage.admission_validation,
            )

    # The publisher copies this immutable, hash-bound projection into the
    # ArtifactVersion row; readers never need the process-local evaluator state.
    projection_payload = {
        "schema_version": "1.0.0",
        "candidate_kind": candidate_kind,
        "candidate_id": expected.candidate_id,
        "candidate_input_hash": expected.input_hash,
        "candidate_output_hash": expected.output_hash,
        "candidate_content_hash": compute_data_artifact_public_payload_hash(expected),
        "quality_input_hash": admitted.snapshot.input_hash,
        "quality_result_id": admitted.snapshot.result_id,
        "quality_result_input_hash": admitted.snapshot.result_input_hash,
        "quality_result_output_hash": admitted.snapshot.result_output_hash,
        "quality_result_content_hash": admitted.snapshot.result_content_hash,
        "evaluation_plan_content_hash": admitted.snapshot.plan_content_hash,
        "evaluation_commitment": admitted.snapshot.evaluation_commitment,
        "bundle_commitment": admitted.snapshot.bundle_commitment,
        "rule_set": {
            "id": admitted.snapshot.rule_set_id,
            "version": admitted.snapshot.rule_set_version,
            "content_hash": admitted.snapshot.rule_set_content_hash,
        },
        "research_contract": {
            "id": admitted.snapshot.contract_id,
            "version": admitted.snapshot.contract_version,
            "content_hash": admitted.snapshot.contract_content_hash,
        },
        "overall_status": admitted.evaluation_result.contract_gate.overall_status.value,
    }
    projection = DataQualityProjection(
        **projection_payload,
        content_hash=compute_canonical_payload_hash(projection_payload),
    )
    validate._data_quality_attestation = _seal_data_quality_attestation(
        expected,
        projection,
    )
    return validate


def _make_snapshot(
    build_result: DataArtifactBuildResult,
    evaluation_input: DataQualityEvaluationInput,
    evaluation_result: DataQualityEvaluationResult,
) -> DataQualityAdmissionSnapshot:
    candidates = (
        build_result.dataset,
        build_result.field_dictionary,
        build_result.source_collection,
    )
    candidate_ids = tuple(item.candidate_id for item in candidates)
    candidate_inputs = tuple(item.input_hash for item in candidates)
    candidate_outputs = tuple(item.output_hash for item in candidates)
    evaluation_commitment = _evaluation_commitment(evaluation_input, evaluation_result)
    bundle_commitment = _bundle_commitment_values(
        candidate_ids=candidate_ids,
        candidate_input_hashes=candidate_inputs,
        candidate_output_hashes=candidate_outputs,
        dataset_canonical_content_hash=build_result.dataset.canonical_content_hash,
        dataset_lineage_hash=build_result.dataset.lineage_hash,
        quality_input_hash=evaluation_input.input_hash,
        quality_result_id=evaluation_result.result_id,
        quality_result_output_hash=evaluation_result.output_hash,
        evaluation_commitment=evaluation_commitment,
    )
    return DataQualityAdmissionSnapshot(
        input_json=evaluation_input.model_dump_json(),
        input_hash=evaluation_input.input_hash,
        result_id=evaluation_result.result_id,
        result_input_hash=evaluation_result.input_hash,
        result_output_hash=evaluation_result.output_hash,
        result_content_hash=evaluation_result.content_hash,
        plan_content_hash=evaluation_result.evaluation_plan.content_hash,
        evaluation_commitment=evaluation_commitment,
        contract_id=evaluation_input.research_contract.id,
        contract_version=evaluation_input.research_contract.version,
        contract_content_hash=evaluation_input.research_contract.content_hash,
        rule_set_id=evaluation_input.quality_rule_set.rule_set_id,
        rule_set_version=evaluation_input.quality_rule_set.version,
        rule_set_content_hash=evaluation_input.quality_rule_set.content_hash,
        candidate_ids=candidate_ids,
        candidate_input_hashes=candidate_inputs,
        candidate_output_hashes=candidate_outputs,
        dataset_canonical_content_hash=build_result.dataset.canonical_content_hash,
        dataset_lineage_hash=build_result.dataset.lineage_hash,
        source_snapshot_ids=build_result.dataset.source_snapshot_ids,
        evidence_ids=build_result.dataset.evidence_ids,
        original_candidate_object_ids=tuple(id(item) for item in candidates),
        bundle_commitment=bundle_commitment,
    )


def _evaluation_commitment(
    evaluation_input: DataQualityEvaluationInput,
    evaluation_result: DataQualityEvaluationResult,
) -> str:
    return compute_canonical_payload_hash(
        {
            "quality_input_hash": evaluation_input.input_hash,
            "quality_result_id": evaluation_result.result_id,
            "quality_result_input_hash": evaluation_result.input_hash,
            "quality_result_output_hash": evaluation_result.output_hash,
            "quality_result_content_hash": evaluation_result.content_hash,
            "quality_plan_content_hash": evaluation_result.evaluation_plan.content_hash,
            "contract": {
                "id": evaluation_input.research_contract.id,
                "version": evaluation_input.research_contract.version,
                "content_hash": evaluation_input.research_contract.content_hash,
            },
            "rule_set": {
                "id": evaluation_input.quality_rule_set.rule_set_id,
                "version": evaluation_input.quality_rule_set.version,
                "content_hash": evaluation_input.quality_rule_set.content_hash,
            },
        }
    )


def _bundle_commitment(snapshot: DataQualityAdmissionSnapshot) -> str:
    return _bundle_commitment_values(
        candidate_ids=snapshot.candidate_ids,
        candidate_input_hashes=snapshot.candidate_input_hashes,
        candidate_output_hashes=snapshot.candidate_output_hashes,
        dataset_canonical_content_hash=snapshot.dataset_canonical_content_hash,
        dataset_lineage_hash=snapshot.dataset_lineage_hash,
        quality_input_hash=snapshot.input_hash,
        quality_result_id=snapshot.result_id,
        quality_result_output_hash=snapshot.result_output_hash,
        evaluation_commitment=snapshot.evaluation_commitment,
    )


def _bundle_commitment_values(
    *,
    candidate_ids: tuple[str, ...],
    candidate_input_hashes: tuple[str, ...],
    candidate_output_hashes: tuple[str, ...],
    dataset_canonical_content_hash: str,
    dataset_lineage_hash: str,
    quality_input_hash: str,
    quality_result_id: str,
    quality_result_output_hash: str,
    evaluation_commitment: str,
) -> str:
    return compute_canonical_payload_hash(
        {
            "candidate_ids": candidate_ids,
            "candidate_input_hashes": candidate_input_hashes,
            "candidate_output_hashes": candidate_output_hashes,
            "dataset_canonical_content_hash": dataset_canonical_content_hash,
            "dataset_lineage_hash": dataset_lineage_hash,
            "quality_input_hash": quality_input_hash,
            "quality_result_id": quality_result_id,
            "quality_result_output_hash": quality_result_output_hash,
            "evaluation_commitment": evaluation_commitment,
        }
    )


__all__ = ["admit_data_artifact_quality", "build_data_quality_publication_validator"]
