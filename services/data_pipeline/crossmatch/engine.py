"""Deterministic cross-source alignment with evidence-bearing decisions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from app.schemas.crossmatch import (
    CandidateEdge,
    CanonicalIdentityValue,
    ConditionOperator,
    ConfidenceBand,
    ConflictGroup,
    CrossmatchCondition,
    CrossmatchAdmissionContext,
    CrossmatchAdmissionSourceContext,
    CrossmatchEvidence,
    CrossmatchInput,
    CrossmatchMethod,
    CrossmatchProducerExecution,
    CrossmatchRecord,
    CrossmatchResult,
    CrossmatchSide,
    EntityCandidate,
    EntityLevel,
    EvidenceLocator,
    MatchDecision,
    PairedMatch,
    UnpairedRecord,
    angular_separation_arcsec,
    compute_crossmatch_condition_id,
    compute_crossmatch_content_hash,
    compute_crossmatch_edge_id,
    compute_crossmatch_edge_logical_match_key,
    compute_crossmatch_evidence_id,
    derive_crossmatch_confidence_band,
    derive_crossmatch_record_semantics,
    group_crossmatch_edge_components,
    within_crossmatch_coordinate_threshold,
)
from app.schemas.manifest import ManifestBundle
from app.schemas.source_acquisition import DataSourceCompletionStatus

from ..manifest import load_frozen_manifest_bundle
from .errors import CrossmatchCapacityError, CrossmatchError
from .identity import normalize_name, normalize_toi_id
from .metrics import compute_crossmatch_metrics
from .normalization import normalize_source_candidates


_TOI_SOURCE_ID = "nasa_exoplanet_archive.toi"
_PS_SOURCE_ID = "nasa_exoplanet_archive.ps"
_HOST_IDENTIFIER_FIELDS = ("star.tic_id", "star.gaia_dr3_id")
_COORDINATE_FIELDS = ("system.right_ascension", "system.declination")


def _within_threshold(separation: float, threshold: float) -> bool:
    """Apply one shared numeric tolerance policy to every coordinate band."""

    return within_crossmatch_coordinate_threshold(separation, threshold)


def align_cross_source_records(input: CrossmatchInput) -> CrossmatchResult:
    """Align two typed acquisition inputs without publishing or mutating Run state."""

    _validate_record_capacity(input)
    bundle = load_frozen_manifest_bundle()
    _validate_source_contract(input, bundle)

    candidates = tuple(
        sorted(
            (
                *normalize_source_candidates(
                    input.left.records,
                    side=CrossmatchSide.left,
                    snapshot=input.left.snapshot,
                    bundle=bundle,
                    rule_set=input.rule_set,
                ),
                *normalize_source_candidates(
                    input.right.records,
                    side=CrossmatchSide.right,
                    snapshot=input.right.snapshot,
                    bundle=bundle,
                    rule_set=input.rule_set,
                ),
            ),
            key=_candidate_sort_key,
        )
    )
    left_hosts = _candidates(candidates, CrossmatchSide.left, EntityLevel.host_star)
    right_hosts = _candidates(candidates, CrossmatchSide.right, EntityLevel.host_star)
    left_planets = _candidates(
        candidates,
        CrossmatchSide.left,
        EntityLevel.planet_candidate,
    )
    right_assertions = _candidates(
        candidates,
        CrossmatchSide.right,
        EntityLevel.planet_assertion,
    )
    _validate_eligible_candidate_capacity(
        input,
        left_hosts=left_hosts,
        right_hosts=right_hosts,
        left_planets=left_planets,
        right_assertions=right_assertions,
    )

    edges: list[CandidateEdge] = []
    evidence: list[CrossmatchEvidence] = []
    conflict_codes: dict[str, str] = {}
    accepted_host_record_pairs: dict[
        tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]],
        tuple[str, ...],
    ] = {}
    conflicting_host_record_pairs: set[
        tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]
    ] = set()

    for left in left_hosts:
        for right in right_hosts:
            built = _match_host_candidates(input, left, right)
            if built is None:
                continue
            edge, item, conflict_code, host_exact_fields = built
            edges.append(edge)
            evidence.append(item)
            if conflict_code:
                conflict_codes[edge.edge_id] = conflict_code
            if edge.decision is MatchDecision.accepted:
                accepted_host_record_pairs[
                    (
                        left.source_record.row_key,
                        right.source_record.row_key,
                    )
                ] = host_exact_fields
            elif edge.decision is MatchDecision.conflict:
                conflicting_host_record_pairs.add(
                    (
                        left.source_record.row_key,
                        right.source_record.row_key,
                    )
                )

    alias_matches: list[tuple[EntityCandidate, EntityCandidate, object, bool]] = []
    host_by_record = {
        (candidate.side, candidate.source_record.row_key): candidate
        for candidate in (*left_hosts, *right_hosts)
    }
    alias_index = _build_alias_index(input)
    for left in left_planets:
        for right in right_assertions:
            entry = _matching_alias(alias_index, left, right)
            if entry is None:
                continue
            host_corroborated = (
                left.source_record.row_key,
                right.source_record.row_key,
            ) in accepted_host_record_pairs
            alias_matches.append((left, right, entry, host_corroborated))

    alias_conflicts = _alias_conflicting_pairs(alias_matches)
    for left, right, entry, host_corroborated in alias_matches:
        is_conflict = (left.candidate_id, right.candidate_id) in alias_conflicts
        is_conflict = (
            is_conflict
            or (
                left.source_record.row_key,
                right.source_record.row_key,
            )
            in conflicting_host_record_pairs
        )
        method = (
            CrossmatchMethod.compound
            if host_corroborated
            else CrossmatchMethod.curated_entity_alias
        )
        if is_conflict:
            decision = MatchDecision.conflict
        elif host_corroborated or not input.rule_set.alias_requires_corroboration:
            decision = MatchDecision.accepted
        else:
            decision = MatchDecision.review_required
        conditions = [
            _condition(
                operator=ConditionOperator.curated_alias,
                field_id="planet.toi_id",
                left_value=_identity(left, "planet.toi_id").normalized_value,
                right_value=_identity(right, "planet.name").normalized_value,
                rule_reference=entry.alias_id,
            )
        ]
        left_host_locators: tuple[EvidenceLocator, ...] = ()
        right_host_locators: tuple[EvidenceLocator, ...] = ()
        if host_corroborated:
            left_host = host_by_record[
                (CrossmatchSide.left, left.source_record.row_key)
            ]
            right_host = host_by_record[
                (CrossmatchSide.right, right.source_record.row_key)
            ]
            corroborating_fields = accepted_host_record_pairs[
                (left.source_record.row_key, right.source_record.row_key)
            ]
            for field_id in corroborating_fields:
                conditions.append(
                    _condition(
                        operator=ConditionOperator.exact,
                        field_id=field_id,
                        left_value=_source_value(left_host, field_id),
                        right_value=_source_value(right_host, field_id),
                        rule_reference=(
                            f"{input.rule_set.rule_set_id}:host_corroboration"
                        ),
                    )
                )
            left_host_locators = tuple(
                _identity(left_host, field_id).locator
                for field_id in corroborating_fields
            )
            right_host_locators = tuple(
                _identity(right_host, field_id).locator
                for field_id in corroborating_fields
            )
        edge, item = _build_edge_and_evidence(
            input,
            left=left,
            right=right,
            entity_level=EntityLevel.planet_candidate,
            method=method,
            decision=decision,
            confidence=(
                0.0
                if is_conflict
                else (
                    input.rule_set.method_confidence.compound
                    if host_corroborated
                    else input.rule_set.method_confidence.curated_entity_alias
                )
            ),
            conditions=tuple(conditions),
            left_locators=(
                _identity(left, "planet.toi_id").locator,
                *left_host_locators,
            ),
            right_locators=(
                _identity(right, "planet.name").locator,
                *right_host_locators,
            ),
        )
        edges.append(edge)
        evidence.append(item)
        if is_conflict:
            conflict_codes[edge.edge_id] = "crossmatch.alias_conflict"

    edges = sorted(edges, key=lambda edge: edge.edge_id)
    evidence = sorted(evidence, key=lambda item: item.evidence_id)
    records = list(
        _records_from_edges(
            edges,
            conflict_codes=conflict_codes,
        )
    )
    participating_candidate_ids = {
        candidate_id
        for edge in edges
        for candidate_id in (edge.left_candidate_id, edge.right_candidate_id)
    }
    records.extend(
        _unpaired_records(
            candidates,
            participating_candidate_ids=participating_candidate_ids,
            left_completion=input.left.completion.status,
            right_completion=input.right.completion.status,
        )
    )
    records = sorted(records, key=_record_sort_key)
    records = list(_apply_manual_decisions(tuple(records), input))

    metrics = compute_crossmatch_metrics(candidates, edges, records, evidence)
    producer = CrossmatchProducerExecution(
        producer_name=input.rule_set.producer_name,
        producer_version=input.rule_set.producer_version,
        rule_set_id=input.rule_set.rule_set_id,
        rule_set_version=input.rule_set.version,
        rule_set_content_hash=input.rule_set.content_hash,
    )
    payload = {
        "schema_version": "1.0.0",
        "input_hash": input.input_hash,
        "case_manifest_id": input.case_manifest_id,
        "case_manifest_version": input.case_manifest_version,
        "case_manifest_content_hash": input.case_manifest_content_hash,
        "field_manifest_id": input.field_manifest_id,
        "field_manifest_version": input.field_manifest_version,
        "field_manifest_content_hash": input.field_manifest_content_hash,
        "left_source_id": input.left.snapshot.source_id,
        "right_source_id": input.right.snapshot.source_id,
        "left_source_mode": input.left.source_mode,
        "right_source_mode": input.right.source_mode,
        "left_data_level": input.left.data_level,
        "right_data_level": input.right.data_level,
        "left_source_snapshot": input.left.snapshot.model_dump(mode="json"),
        "right_source_snapshot": input.right.snapshot.model_dump(mode="json"),
        "left_completion": input.left.completion.model_dump(mode="json"),
        "right_completion": input.right.completion.model_dump(mode="json"),
        "rule_set_id": input.rule_set.rule_set_id,
        "rule_set_version": input.rule_set.version,
        "rule_set_content_hash": input.rule_set.content_hash,
        "alias_catalog_id": input.alias_catalog.catalog_id,
        "alias_catalog_version": input.alias_catalog.version,
        "alias_catalog_content_hash": input.alias_catalog.content_hash,
        "admission_context": CrossmatchAdmissionContext(
            source_input_hash=input.source_input_hash,
            rule_set=input.rule_set,
            alias_catalog=input.alias_catalog,
            source_policy=input.source_policy,
            left=CrossmatchAdmissionSourceContext(
                source_mode=input.left.source_mode,
                data_level=input.left.data_level,
                source_snapshot_id=input.left.snapshot.snapshot_id,
                source_snapshot_content_hash=input.left.snapshot.content_hash,
                source_id=input.left.snapshot.source_id,
                query_hash=input.left.snapshot.query_hash,
                completion=input.left.completion,
            ),
            right=CrossmatchAdmissionSourceContext(
                source_mode=input.right.source_mode,
                data_level=input.right.data_level,
                source_snapshot_id=input.right.snapshot.snapshot_id,
                source_snapshot_content_hash=input.right.snapshot.content_hash,
                source_id=input.right.snapshot.source_id,
                query_hash=input.right.snapshot.query_hash,
                completion=input.right.completion,
            ),
            manual_review_decisions=input.manual_review_decisions,
        ).model_dump(mode="json"),
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
        "candidate_edges": [edge.model_dump(mode="json") for edge in edges],
        "evidence": [item.model_dump(mode="json") for item in evidence],
        "records": [record.model_dump(mode="json") for record in records],
        "metrics": metrics.model_dump(mode="json"),
        "producer_execution": producer.model_dump(mode="json"),
    }
    content_hash = compute_crossmatch_content_hash(payload)
    return CrossmatchResult.model_validate(
        {
            "result_id": f"crossmatch.{content_hash.removeprefix('sha256:')[:24]}",
            "output_hash": content_hash,
            "content_hash": content_hash,
            **payload,
        }
    )


def _validate_record_capacity(input: CrossmatchInput) -> None:
    capacity = input.rule_set.capacity
    left_count = len(input.left.records)
    right_count = len(input.right.records)
    if (
        left_count > capacity.max_left_records
        or right_count > capacity.max_right_records
    ):
        raise CrossmatchCapacityError(
            "CROSSMATCH_CAPACITY_EXCEEDED",
            "crossmatch input exceeds the frozen capacity policy",
        )


def _validate_eligible_candidate_capacity(
    input: CrossmatchInput,
    *,
    left_hosts: tuple[EntityCandidate, ...],
    right_hosts: tuple[EntityCandidate, ...],
    left_planets: tuple[EntityCandidate, ...],
    right_assertions: tuple[EntityCandidate, ...],
) -> None:
    eligible_candidate_pairs = len(left_hosts) * len(right_hosts) + len(
        left_planets
    ) * len(right_assertions)
    if eligible_candidate_pairs > input.rule_set.capacity.max_candidate_pairs:
        raise CrossmatchCapacityError(
            "CROSSMATCH_CAPACITY_EXCEEDED",
            "crossmatch candidates exceed the frozen capacity policy",
        )


def _validate_source_contract(
    input: CrossmatchInput,
    bundle: ManifestBundle,
) -> None:
    expected_sources = (_TOI_SOURCE_ID, _PS_SOURCE_ID)
    actual_sources = (
        input.left.snapshot.source_id,
        input.right.snapshot.source_id,
    )
    if actual_sources != expected_sources:
        raise CrossmatchError(
            "CROSSMATCH_SOURCE_CONTRACT_MISMATCH",
            "Cross-source Entity Alignment requires TOI as left and PS as right input",
        )
    manifest_source_ids = {source.source_id for source in bundle.field_manifest.sources}
    if not set(actual_sources).issubset(manifest_source_ids):
        raise CrossmatchError(
            "CROSSMATCH_SOURCE_CONTRACT_MISMATCH",
            "crossmatch source is absent from the frozen Field Manifest",
        )


def _match_host_candidates(
    input: CrossmatchInput,
    left: EntityCandidate,
    right: EntityCandidate,
) -> tuple[CandidateEdge, CrossmatchEvidence, str | None, tuple[str, ...]] | None:
    exact_fields: list[str] = []
    conflicting_fields: list[str] = []
    for field_id in _HOST_IDENTIFIER_FIELDS:
        left_value = _optional_identity(left, field_id)
        right_value = _optional_identity(right, field_id)
        if left_value is None or right_value is None:
            continue
        if left_value.normalized_value == right_value.normalized_value:
            exact_fields.append(field_id)
        else:
            conflicting_fields.append(field_id)

    separation = None
    if left.coordinate is not None and right.coordinate is not None:
        separation = angular_separation_arcsec(left.coordinate, right.coordinate)
    strict_threshold = input.rule_set.coordinate.strict_separation_arcsec
    coordinate_threshold = input.rule_set.coordinate.manual_review_separation_arcsec
    coordinate_match = separation is not None and _within_threshold(
        separation, coordinate_threshold
    )
    coordinate_conflict = (
        separation is not None
        and not coordinate_match
        and separation > coordinate_threshold
        and bool(exact_fields)
    )
    if not exact_fields and not coordinate_match:
        return None

    conditions: list[CrossmatchCondition] = []
    left_locators: list[EvidenceLocator] = []
    right_locators: list[EvidenceLocator] = []
    for field_id in exact_fields:
        left_value = _identity(left, field_id)
        right_value = _identity(right, field_id)
        conditions.append(
            _condition(
                operator=ConditionOperator.exact,
                field_id=field_id,
                left_value=left_value.normalized_value,
                right_value=right_value.normalized_value,
                rule_reference=f"{input.rule_set.rule_set_id}:exact_identifier",
            )
        )
        left_locators.append(left_value.locator)
        right_locators.append(right_value.locator)
    for field_id in conflicting_fields:
        left_value = _identity(left, field_id)
        right_value = _identity(right, field_id)
        conditions.append(
            _condition(
                operator=ConditionOperator.contradicts,
                field_id=field_id,
                left_value=left_value.normalized_value,
                right_value=right_value.normalized_value,
                rule_reference=f"{input.rule_set.rule_set_id}:identifier_conflict",
            )
        )
        left_locators.append(left_value.locator)
        right_locators.append(right_value.locator)
    if coordinate_match:
        conditions.append(
            _condition(
                operator=ConditionOperator.angular_separation_lte,
                field_id=None,
                separation_arcsec=separation,
                strict_threshold_arcsec=strict_threshold,
                manual_review_threshold_arcsec=coordinate_threshold,
                rule_reference=f"{input.rule_set.rule_set_id}:coordinate",
            )
        )
        for field_id in _COORDINATE_FIELDS:
            left_locators.append(_identity(left, field_id).locator)
            right_locators.append(_identity(right, field_id).locator)
    elif coordinate_conflict:
        conditions.append(
            _condition(
                operator=ConditionOperator.angular_separation_gt,
                field_id=None,
                separation_arcsec=separation,
                strict_threshold_arcsec=strict_threshold,
                manual_review_threshold_arcsec=coordinate_threshold,
                rule_reference=f"{input.rule_set.rule_set_id}:coordinate_conflict",
            )
        )
        for field_id in _COORDINATE_FIELDS:
            left_locators.append(_identity(left, field_id).locator)
            right_locators.append(_identity(right, field_id).locator)

    if conflicting_fields or coordinate_conflict:
        method = (
            CrossmatchMethod.compound
            if exact_fields or coordinate_match
            else CrossmatchMethod.exact_identifier
        )
        decision = MatchDecision.conflict
        confidence = 0.0
        conflict_code = (
            "crossmatch.identifier_conflict"
            if conflicting_fields
            else "crossmatch.identifier_coordinate_conflict"
        )
    elif exact_fields:
        method = CrossmatchMethod.exact_identifier
        decision = MatchDecision.accepted
        confidence = input.rule_set.method_confidence.exact_identifier
        conflict_code = None
    else:
        method = CrossmatchMethod.coordinate
        decision = MatchDecision.review_required
        confidence = (
            input.rule_set.method_confidence.coordinate_strict
            if separation is not None
            and _within_threshold(separation, strict_threshold)
            else input.rule_set.method_confidence.coordinate_review
        )
        conflict_code = None

    edge, evidence = _build_edge_and_evidence(
        input,
        left=left,
        right=right,
        entity_level=EntityLevel.host_star,
        method=method,
        decision=decision,
        confidence=confidence,
        conditions=tuple(conditions),
        left_locators=tuple(_dedupe_locators(left_locators)),
        right_locators=tuple(_dedupe_locators(right_locators)),
    )
    return edge, evidence, conflict_code, tuple(exact_fields)


def _build_alias_index(
    input: CrossmatchInput,
) -> dict[tuple[str, str, str, str], object]:
    """Index planet alias entries once; first catalog entry wins per key."""

    index: dict[tuple[str, str, str, str], object] = {}
    for entry in input.alias_catalog.entries:
        if (
            entry.entity_level is EntityLevel.planet_candidate
            and entry.left_field_id == "planet.toi_id"
            and entry.right_field_id == "planet.name"
        ):
            key = (
                entry.left_source_id,
                entry.right_source_id,
                normalize_toi_id(entry.left_value),
                normalize_name(entry.right_value),
            )
            index.setdefault(key, entry)
    return index


def _matching_alias(
    alias_index: dict[tuple[str, str, str, str], object],
    left: EntityCandidate,
    right: EntityCandidate,
):
    key = (
        left.source_record.source_id,
        right.source_record.source_id,
        _identity(left, "planet.toi_id").normalized_value,
        _identity(right, "planet.name").normalized_value,
    )
    return alias_index.get(key)


def _alias_conflicting_pairs(alias_matches) -> set[tuple[str, str]]:
    right_values_by_left: dict[str, set[str]] = defaultdict(set)
    left_values_by_right: dict[str, set[str]] = defaultdict(set)
    for left, right, _, _ in alias_matches:
        right_values_by_left[left.candidate_id].add(
            _identity(right, "planet.name").normalized_value
        )
        left_values_by_right[_identity(right, "planet.name").normalized_value].add(
            _identity(left, "planet.toi_id").normalized_value
        )
    conflicts: set[tuple[str, str]] = set()
    for left, right, _, _ in alias_matches:
        right_name = _identity(right, "planet.name").normalized_value
        if (
            len(right_values_by_left[left.candidate_id]) > 1
            or len(left_values_by_right[right_name]) > 1
        ):
            conflicts.add((left.candidate_id, right.candidate_id))
    return conflicts


def _build_edge_and_evidence(
    input: CrossmatchInput,
    *,
    left: EntityCandidate,
    right: EntityCandidate,
    entity_level: EntityLevel,
    method: CrossmatchMethod,
    decision: MatchDecision,
    confidence: float,
    conditions: tuple[CrossmatchCondition, ...],
    left_locators: tuple[EvidenceLocator, ...],
    right_locators: tuple[EvidenceLocator, ...],
) -> tuple[CandidateEdge, CrossmatchEvidence]:
    logical_match_key = _logical_match_key(
        entity_level,
        (left,),
        (right,),
    )
    confidence_band = _confidence_band(input, confidence, decision)
    evidence_payload = {
        "evidence_id": compute_crossmatch_evidence_id(
            logical_match_key=logical_match_key,
            method=method,
            decision=decision,
            condition_ids=(condition.condition_id for condition in conditions),
            rule_set_content_hash=input.rule_set.content_hash,
        ),
        "entity_level": entity_level,
        "method": method,
        "decision": decision,
        "confidence": confidence,
        "confidence_band": confidence_band,
        "left_candidate_id": left.candidate_id,
        "right_candidate_id": right.candidate_id,
        "left_locators": [
            locator.model_dump(mode="json")
            for locator in _dedupe_locators(left_locators)
        ],
        "right_locators": [
            locator.model_dump(mode="json")
            for locator in _dedupe_locators(right_locators)
        ],
        "conditions": [condition.model_dump(mode="json") for condition in conditions],
        "rule_set_id": input.rule_set.rule_set_id,
        "rule_set_version": input.rule_set.version,
        "rule_set_content_hash": input.rule_set.content_hash,
    }
    evidence = CrossmatchEvidence.model_validate(_with_hash(evidence_payload))
    edge_payload = {
        "edge_id": compute_crossmatch_edge_id(
            logical_match_key=logical_match_key,
            method=method,
            decision=decision,
            evidence_id=evidence.evidence_id,
        ),
        "logical_match_key": logical_match_key,
        "entity_level": entity_level,
        "left_candidate_id": left.candidate_id,
        "right_candidate_id": right.candidate_id,
        "method": method,
        "decision": decision,
        "confidence": confidence,
        "confidence_band": confidence_band,
        "condition_ids": [condition.condition_id for condition in conditions],
        "evidence_ids": [evidence.evidence_id],
    }
    return CandidateEdge.model_validate(_with_hash(edge_payload)), evidence


def _records_from_edges(
    edges: list[CandidateEdge],
    *,
    conflict_codes: dict[str, str],
) -> tuple[PairedMatch | ConflictGroup, ...]:
    records: list[PairedMatch | ConflictGroup] = []
    for component in group_crossmatch_edge_components(edges):
        semantics = derive_crossmatch_record_semantics(component)
        if semantics.record_type == "conflict_group":
            codes = sorted(
                {
                    conflict_codes.get(edge.edge_id, "crossmatch.candidate_conflict")
                    for edge in component
                }
            )
            payload = {
                "record_type": "conflict_group",
                "logical_match_key": semantics.logical_match_key,
                "entity_level": semantics.entity_level,
                "left_candidate_ids": semantics.left_candidate_ids,
                "right_candidate_ids": semantics.right_candidate_ids,
                "method": semantics.method,
                "decision": semantics.decision,
                "conflict_code": codes[0],
                "evidence_ids": semantics.evidence_ids,
            }
            records.append(ConflictGroup.model_validate(_with_hash(payload)))
            continue

        payload = {
            "record_type": "paired",
            "logical_match_key": semantics.logical_match_key,
            "entity_level": semantics.entity_level,
            "topology": semantics.topology,
            "left_candidate_ids": semantics.left_candidate_ids,
            "right_candidate_ids": semantics.right_candidate_ids,
            "method": semantics.method,
            "decision": semantics.decision,
            "confidence_band": semantics.confidence_band,
            "evidence_ids": semantics.evidence_ids,
        }
        records.append(PairedMatch.model_validate(_with_hash(payload)))
    return tuple(records)


def _unpaired_records(
    candidates: tuple[EntityCandidate, ...],
    *,
    participating_candidate_ids: set[str],
    left_completion: DataSourceCompletionStatus,
    right_completion: DataSourceCompletionStatus,
) -> tuple[UnpairedRecord, ...]:
    records: list[UnpairedRecord] = []
    for candidate in candidates:
        if candidate.candidate_id in participating_candidate_ids:
            continue
        opposite_completion = (
            right_completion
            if candidate.side is CrossmatchSide.left
            else left_completion
        )
        decision = (
            MatchDecision.unmatched
            if opposite_completion is DataSourceCompletionStatus.complete
            else MatchDecision.inconclusive
        )
        payload = {
            "record_type": "unpaired",
            "candidate_id": candidate.candidate_id,
            "side": candidate.side,
            "entity_level": candidate.entity_level,
            "decision": decision,
            "source_completion_status": opposite_completion.value,
            "reason": (
                "no candidate in a complete opposite source scope"
                if decision is MatchDecision.unmatched
                else "opposite source scope is incomplete"
            ),
        }
        records.append(UnpairedRecord.model_validate(_with_hash(payload)))
    return tuple(records)


def _apply_manual_decisions(
    records: tuple[CrossmatchRecord, ...],
    input: CrossmatchInput,
) -> tuple[CrossmatchRecord, ...]:
    decisions = {
        decision.logical_match_key: decision
        for decision in input.manual_review_decisions
    }
    if not decisions:
        return records
    applied: set[str] = set()
    updated: list[CrossmatchRecord] = []
    for record in records:
        if isinstance(record, UnpairedRecord):
            updated.append(record)
            continue
        decision = decisions.get(record.logical_match_key)
        if decision is None:
            updated.append(record)
            continue
        if (
            isinstance(record, PairedMatch)
            and record.decision is MatchDecision.accepted
        ):
            raise CrossmatchError(
                "CROSSMATCH_MANUAL_DECISION_NOT_REVIEWABLE",
                "manual decisions may target only review or conflict records",
            )
        if (
            set(decision.left_candidate_ids) != set(record.left_candidate_ids)
            or set(decision.right_candidate_ids) != set(record.right_candidate_ids)
            or set(decision.evidence_ids) != set(record.evidence_ids)
        ):
            raise CrossmatchError(
                "CROSSMATCH_MANUAL_DECISION_BINDING_MISMATCH",
                "manual decision candidate or Evidence binding disagrees with result",
            )
        payload = record.model_dump(mode="json", exclude={"content_hash"})
        serialized_decision = decision.model_dump(mode="json")
        payload.update(
            {
                "manual_decision_id": serialized_decision["decision_id"],
                "adjudication": serialized_decision["adjudication"],
                "adjudicated_by": serialized_decision["adjudicated_by"],
                "reviewer_kind": serialized_decision["reviewer_kind"],
                "adjudication_rule_or_actor": (
                    serialized_decision["adjudication_rule_or_actor"]
                ),
                "adjudicated_at": serialized_decision["adjudicated_at"],
                "adjudication_rationale": serialized_decision["rationale"],
                "manual_decision_content_hash": serialized_decision["content_hash"],
            }
        )
        model = PairedMatch if isinstance(record, PairedMatch) else ConflictGroup
        updated.append(model.model_validate(_with_hash(payload)))
        applied.add(record.logical_match_key)
    missing = sorted(set(decisions) - applied)
    if missing:
        raise CrossmatchError(
            "CROSSMATCH_MANUAL_DECISION_TARGET_MISSING",
            "manual decision does not target a reviewable result",
        )
    return tuple(updated)


def _condition(
    *,
    operator: ConditionOperator,
    field_id: str | None,
    rule_reference: str,
    left_value=None,
    right_value=None,
    separation_arcsec: float | None = None,
    strict_threshold_arcsec: float | None = None,
    manual_review_threshold_arcsec: float | None = None,
) -> CrossmatchCondition:
    payload = {
        "operator": operator,
        "field_id": field_id,
        "left_value": left_value,
        "right_value": right_value,
        "separation_arcsec": separation_arcsec,
        "strict_threshold_arcsec": strict_threshold_arcsec,
        "manual_review_threshold_arcsec": manual_review_threshold_arcsec,
        "rule_reference": rule_reference,
    }
    return CrossmatchCondition(
        condition_id=compute_crossmatch_condition_id(payload),
        **payload,
    )


def _identity(
    candidate: EntityCandidate,
    field_id: str,
) -> CanonicalIdentityValue:
    value = _optional_identity(candidate, field_id)
    if value is None:
        raise CrossmatchError(
            "CROSSMATCH_INTERNAL_EVIDENCE_MISSING",
            f"candidate lacks required identity Evidence: {field_id}",
        )
    return value


def _optional_identity(
    candidate: EntityCandidate,
    field_id: str,
) -> CanonicalIdentityValue | None:
    return next(
        (value for value in candidate.identity_values if value.field_id == field_id),
        None,
    )


def _source_value(candidate: EntityCandidate, field_id: str) -> str | None:
    value = _optional_identity(candidate, field_id)
    return value.normalized_value if value is not None else None


def _dedupe_locators(
    locators: Iterable[EvidenceLocator],
) -> tuple[EvidenceLocator, ...]:
    unique: dict[tuple, EvidenceLocator] = {}
    for locator in locators:
        key = (
            locator.side.value,
            locator.source_snapshot_id,
            locator.source_id,
            locator.query_hash,
            locator.row_key,
            locator.raw_field,
        )
        unique[key] = locator
    return tuple(unique[key] for key in sorted(unique))


def _logical_match_key(
    entity_level: EntityLevel,
    left: tuple[EntityCandidate, ...],
    right: tuple[EntityCandidate, ...],
) -> str:
    return compute_crossmatch_edge_logical_match_key(entity_level, left, right)


def _confidence_band(
    input: CrossmatchInput,
    confidence: float,
    decision: MatchDecision,
) -> ConfidenceBand:
    return derive_crossmatch_confidence_band(
        input.rule_set,
        confidence,
        decision,
    )


def _with_hash(payload: dict) -> dict:
    result = dict(payload)
    result["content_hash"] = compute_crossmatch_content_hash(result)
    return result


def _candidates(
    candidates: tuple[EntityCandidate, ...],
    side: CrossmatchSide,
    level: EntityLevel,
) -> tuple[EntityCandidate, ...]:
    return tuple(
        candidate
        for candidate in candidates
        if candidate.side is side and candidate.entity_level is level
    )


def _candidate_sort_key(candidate: EntityCandidate) -> tuple:
    return (
        candidate.side.value,
        candidate.entity_level.value,
        candidate.source_record.source_id,
        candidate.source_record.row_key,
        candidate.candidate_id,
    )


def _record_sort_key(record: CrossmatchRecord) -> tuple:
    logical_key = (
        record.candidate_id
        if isinstance(record, UnpairedRecord)
        else record.logical_match_key
    )
    return (record.entity_level.value, record.record_type, logical_key)
