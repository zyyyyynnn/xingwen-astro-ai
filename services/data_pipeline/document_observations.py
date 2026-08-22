"""Pure document observation pipeline.

Deterministic, typed transformation from one persisted canonical
``DocumentParseCandidate`` into raw ``ScientificDataExtractionCandidate``
observations and admitted ``TypedDocumentObservation`` values. This module
performs no database access and no publication; persistence facts are supplied
by the caller and consumed only as frozen identity context.

Authority boundaries honored here:
- Field labels resolve ONLY through exact canonical ids or exact normalized
  registered ``DocumentFieldAlias`` entries owned by the Field Manifest.
- Entities bind ONLY through exact unique matches against the frozen
  crossmatch identity rows. No crossmatch is re-run and no canonical
  object is created.
- Scalar semantics (symmetric/asymmetric uncertainty, upper/lower limits,
  explicit nulls) are parsed exactly once, here. Downstream projection never
  re-interprets the free text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import DocumentSourcePolicy
from app.schemas.crossmatch import (
    CrossmatchRecord,
    CrossmatchResult,
    UnpairedRecord,
    compute_crossmatch_record_logical_key,
)
from app.schemas.data_artifacts import (
    DataArtifactErrorCode,
    DataSourceSnapshotProjection,
    DocumentObservationAdmissionCode,
    DocumentObservationAdmissionStatus,
    LimitStatus,
    TypedDocumentObservation,
)
from app.schemas.document_observation_rules import (
    DocumentObservationRuleSet,
    LimitTokenDirection,
)
from app.schemas.manifest import (
    CanonicalFieldId,
    FieldDefinition,
    ManifestBundle,
    NullReason,
    normalize_document_alias_label,
)
from app.schemas.scientific_document import (
    DocumentLocator,
    DocumentParseCandidate,
    DocumentParseQuality,
    DocumentTable,
    ScientificDataExtractionCandidate,
    TextSpan,
)

from .crossmatch.identity import (
    normalize_gaia_dr3_id,
    normalize_name,
    normalize_tic_id,
    normalize_toi_id,
)
from .data_artifacts.conversion import decimal_from_source
from .data_artifacts.errors import DataArtifactError


@dataclass(frozen=True, slots=True)
class PersistedDocumentContext:
    """Frozen persisted identities binding one parse to its provenance."""

    research_input_id: str
    document_parse_id: str
    #: Persisted SourceSnapshot UUID reused through ArtifactSourceSnapshotBinding.
    source_snapshot_id: str


@dataclass(frozen=True, slots=True)
class RawExtractionBatch:
    """Complete pure output for one persisted parse."""

    raw_candidates: tuple[ScientificDataExtractionCandidate, ...]
    accepted: tuple[TypedDocumentObservation, ...]
    outcomes: tuple["DocumentObservationOutcome", ...]
    producer_output_summary: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DocumentObservationOutcome:
    """One admission outcome per extracted observation."""

    raw_candidate_id: str
    status: DocumentObservationAdmissionStatus
    code: DocumentObservationAdmissionCode | None


class DocumentObservationError(RuntimeError):
    """Raised when caller-supplied frozen facts violate the input contract."""


def _observation_region_quality(
    *qualities: DocumentParseQuality,
) -> DocumentParseQuality:
    """Propagate parse quality across the regions forming one observation."""

    if any(quality is DocumentParseQuality.unsupported for quality in qualities):
        raise DocumentObservationError(
            "unsupported parse regions cannot form a scientific observation"
        )
    if any(quality is DocumentParseQuality.partial for quality in qualities):
        return DocumentParseQuality.partial
    if all(quality is DocumentParseQuality.accepted for quality in qualities):
        return DocumentParseQuality.accepted
    raise DocumentObservationError("unrecognized observation region quality")


def extract_document_observations(
    *,
    parse: DocumentParseCandidate,
    context: PersistedDocumentContext,
    snapshot_projection: DataSourceSnapshotProjection,
    contract_policy: DocumentSourcePolicy,
    case_capability: bool,
    requested_fields: tuple[CanonicalFieldId, ...],
    manifests: ManifestBundle,
    crossmatch: CrossmatchResult,
    rules: DocumentObservationRuleSet,
) -> RawExtractionBatch:
    """Run the complete deterministic document-to-observation transformation."""

    if context.research_input_id != parse.research_input_id:
        raise DocumentObservationError(
            "persisted ResearchInput does not match the canonical parse"
        )
    resolver = _Resolver(
        manifests=manifests,
        requested_fields=requested_fields,
    )
    entities = _EntityIndex(crossmatch=crossmatch)
    extractor = _Extractor(
        context=context,
        resolver=resolver,
        entities=entities,
        rules=rules,
    )

    authorization_code = _authorization_rejection(
        policy=contract_policy,
        case_capability=case_capability,
        manifests=manifests,
    )
    raw_candidates: list[ScientificDataExtractionCandidate] = []
    accepted: list[TypedDocumentObservation] = []
    outcomes: list[DocumentObservationOutcome] = []

    def record_unsupported(table: DocumentTable) -> None:
        _guard_capacity(len(raw_candidates), len(outcomes), rules)
        region_hash = compute_canonical_payload_hash(
            {
                "document_parse_id": context.document_parse_id,
                "table_id": table.table_id,
            }
        ).removeprefix("sha256:")
        outcomes.append(
            DocumentObservationOutcome(
                raw_candidate_id=f"document.parse.unsupported.{region_hash[:24]}",
                status=DocumentObservationAdmissionStatus.rejected,
                code=(DocumentObservationAdmissionCode.document_parse_unsupported),
            )
        )

    for table in sorted(parse.tables, key=lambda item: item.table_id):
        if table.quality is DocumentParseQuality.unsupported:
            record_unsupported(table)
            continue
        for draft in extractor.table_drafts(table):
            _record_draft(
                draft,
                parse=parse,
                context=context,
                snapshot_projection=snapshot_projection,
                authorization_code=authorization_code,
                raw_candidates=raw_candidates,
                accepted=accepted,
                outcomes=outcomes,
                rules=rules,
            )
    for draft in extractor.text_drafts(parse):
        _record_draft(
            draft,
            parse=parse,
            context=context,
            snapshot_projection=snapshot_projection,
            authorization_code=authorization_code,
            raw_candidates=raw_candidates,
            accepted=accepted,
            outcomes=outcomes,
            rules=rules,
        )

    producer_output_summary = {
        "raw_candidate_count": len(raw_candidates),
        "accepted_count": len(accepted),
        "raw_candidates": [
            item.model_dump(mode="json", exclude={"created_at"})
            for item in sorted(raw_candidates, key=lambda item: item.candidate_id)
        ],
        "accepted_observations": [
            item.model_dump(mode="json")
            for item in sorted(accepted, key=lambda item: item.observation_id)
        ],
        "outcomes": [
            {
                "raw_candidate_id": item.raw_candidate_id,
                "status": item.status.value,
                "code": item.code.value if item.code is not None else None,
            }
            for item in sorted(
                outcomes,
                key=lambda item: (item.raw_candidate_id, item.status.value),
            )
        ],
    }
    return RawExtractionBatch(
        raw_candidates=tuple(raw_candidates),
        accepted=tuple(accepted),
        outcomes=tuple(outcomes),
        producer_output_summary=producer_output_summary,
    )


def _guard_capacity(extracted: int, recorded: int, rules) -> None:
    limit = rules.max_observations_per_parse
    if max(extracted, recorded) >= limit:
        raise DataArtifactError(
            DataArtifactErrorCode.capacity_exceeded,
            "document observation capacity exceeded",
        )


def _authorization_rejection(
    *,
    policy: DocumentSourcePolicy,
    case_capability: bool,
    manifests: ManifestBundle,
) -> DocumentObservationAdmissionCode | None:
    if policy is DocumentSourcePolicy.disabled:
        return DocumentObservationAdmissionCode.document_source_disabled
    if not case_capability:
        return DocumentObservationAdmissionCode.document_source_capability_unsupported
    return None


def _record_draft(
    draft: "_Draft",
    *,
    parse: DocumentParseCandidate,
    context: PersistedDocumentContext,
    snapshot_projection: DataSourceSnapshotProjection,
    authorization_code: DocumentObservationAdmissionCode | None,
    raw_candidates: list[ScientificDataExtractionCandidate],
    accepted: list[TypedDocumentObservation],
    outcomes: list[DocumentObservationOutcome],
    rules: DocumentObservationRuleSet,
) -> None:
    _guard_capacity(len(raw_candidates), len(outcomes), rules)
    code = draft.admit(authorization_code)
    candidate = draft.to_raw_candidate(created_at=parse.created_at)
    raw_candidates.append(candidate)
    if code is None:
        observation = draft.to_typed_observation(
            context=context,
            snapshot_projection=snapshot_projection,
        )
        accepted.append(observation)
        status = DocumentObservationAdmissionStatus.accepted
    elif code in (
        DocumentObservationAdmissionCode.document_field_unresolved,
        DocumentObservationAdmissionCode.document_field_ambiguous,
        DocumentObservationAdmissionCode.document_entity_unresolved,
        DocumentObservationAdmissionCode.document_entity_ambiguous,
        DocumentObservationAdmissionCode.document_unit_unresolved,
    ):
        # Well-formed observation whose scientific coordinates could not be
        # closed uniquely: deterministically reviewable, never auto-selected.
        status = DocumentObservationAdmissionStatus.review_required
    else:
        status = DocumentObservationAdmissionStatus.rejected
    outcomes.append(
        DocumentObservationOutcome(
            raw_candidate_id=candidate.candidate_id,
            status=status,
            code=code,
        )
    )


class _Draft:
    """Working state and admission ladder for one extracted observation."""

    __slots__ = (
        "context",
        "resolver",
        "entities",
        "rules",
        "locator",
        "parse_quality",
        "raw_text",
        "raw_unit_token",
        "entity_token",
        "row_context",
        "header_context",
        "preresolved_field",
        "field_candidates",
        "resolved_field",
        "logical_key",
        "parsed_scalar",
        "positive_error",
        "negative_error",
        "limit_status",
        "null_status",
        "unit_id",
        "candidate_id",
    )

    def __init__(
        self,
        *,
        context: PersistedDocumentContext,
        resolver: "_Resolver",
        entities: "_EntityIndex",
        rules: DocumentObservationRuleSet,
        locator: DocumentLocator,
        parse_quality: DocumentParseQuality,
        raw_text: str,
        header_context: str | None,
        header_unit_token: str | None,
        entity_token: str | None,
        row_context: tuple[tuple[str, str], ...],
        field_candidates: tuple["FieldDefinition", ...] | None = None,
    ) -> None:
        # ``header_context`` carries the raw header/pattern label for provenance;
        # ``preresolved_field`` is set by the exact table-header resolution.
        self.context = context
        self.resolver = resolver
        self.entities = entities
        self.rules = rules
        self.locator = locator
        self.parse_quality = parse_quality
        self.raw_text = raw_text
        self.raw_unit_token = header_unit_token
        self.entity_token = entity_token
        self.row_context = row_context
        self.header_context = header_context
        self.preresolved_field: FieldDefinition | None = None
        # Exact header-resolution candidates spanning object domains; the
        # admission ladder scopes them through the resolved entity context.
        self.field_candidates = tuple(field_candidates) if field_candidates else None
        self.resolved_field: FieldDefinition | None = None
        self.logical_key: str | None = None
        self.parsed_scalar: Decimal | None = None
        self.positive_error: Decimal | None = None
        self.negative_error: Decimal | None = None
        self.limit_status = LimitStatus.not_applicable
        self.null_status: NullReason | None = None
        self.unit_id: str | None = None
        self.candidate_id = ""

    def admit(
        self, authorization_code: DocumentObservationAdmissionCode | None
    ) -> DocumentObservationAdmissionCode | None:
        """Close authorization, field, entity, value and unit; return outcome."""

        code = authorization_code or self._resolve_field()
        code = code or self._resolve_entity()
        code = code or self._parse_value()
        code = code or self._resolve_unit()
        # Identity depends only on frozen parse facts and the actual RuleSet;
        # admission outcome never changes it and created_at never enters it.
        self.candidate_id = self._derive_candidate_id()
        return code

    def _resolve_field(self) -> DocumentObservationAdmissionCode | None:
        if self.preresolved_field is not None:
            self.resolved_field = self.preresolved_field
            return None
        assert self.raw_text is not None
        if self.field_candidates is not None:
            matches = list(self.field_candidates)
        else:
            label_source = self.header_context or self.raw_text
            matches = self.resolver.fields_for_label(label_source)
        if not matches:
            return DocumentObservationAdmissionCode.document_field_unresolved
        if self.entity_token:
            object_type = self.entities.object_type_for_token(self.entity_token)
            if object_type is not None:
                scoped = [
                    field for field in matches if field.object_type.value == object_type
                ]
                if scoped:
                    matches = scoped
        if len(matches) > 1:
            return DocumentObservationAdmissionCode.document_field_ambiguous
        self.resolved_field = matches[0]
        return None

    def _resolve_entity(self) -> DocumentObservationAdmissionCode | None:
        if not self.entity_token:
            return DocumentObservationAdmissionCode.document_entity_unresolved
        assert self.resolved_field is not None
        key, status = self.entities.exact_unique_match(
            self.entity_token, self.resolved_field.object_type.value
        )
        if key is None:
            if status == "ambiguous":
                return DocumentObservationAdmissionCode.document_entity_ambiguous
            return DocumentObservationAdmissionCode.document_entity_unresolved
        self.logical_key = key
        return None

    def _parse_value(self) -> DocumentObservationAdmissionCode | None:
        text = self.raw_text.strip()
        lowered = normalize_document_alias_label(text)
        null_tokens = {
            normalize_document_alias_label(token) for token in self.rules.null_tokens
        }
        if lowered in null_tokens:
            self.null_status = NullReason.not_measured
            return None
        asymmetric = re.match(self.rules.asymmetric_pattern, text)
        if asymmetric is not None:
            try:
                self.parsed_scalar = decimal_from_source(asymmetric.group("value"))
                self.positive_error = decimal_from_source(asymmetric.group("pos"))
                self.negative_error = decimal_from_source(asymmetric.group("neg"))
            except (DataArtifactError, InvalidOperation):
                return DocumentObservationAdmissionCode.document_value_invalid
            inline_unit = (asymmetric.groupdict().get("unit") or "").strip()
            if inline_unit:
                self.raw_unit_token = inline_unit
            return None
        numeric = re.match(self.rules.numeric_pattern, text)
        if numeric is None:
            return DocumentObservationAdmissionCode.document_value_invalid
        limit_prefix = numeric.group("limit")
        try:
            self.parsed_scalar = decimal_from_source(numeric.group("value"))
            symmetric = numeric.group("sym")
            if symmetric is not None:
                self.positive_error = decimal_from_source(symmetric)
                self.negative_error = decimal_from_source(symmetric)
        except (DataArtifactError, InvalidOperation):
            return DocumentObservationAdmissionCode.document_value_invalid
        inline_unit = (numeric.groupdict().get("unit") or "").strip()
        if inline_unit:
            self.raw_unit_token = inline_unit
        if limit_prefix is not None:
            direction = self.rules_limit_direction(limit_prefix)
            if direction is None:
                return DocumentObservationAdmissionCode.document_value_invalid
            self.limit_status = (
                LimitStatus.upper_limit
                if direction is LimitTokenDirection.upper
                else LimitStatus.lower_limit
            )
        return None

    def rules_limit_direction(self, prefix: str) -> LimitTokenDirection | None:
        tokens = {item.token: item.direction for item in self.rules.limit_tokens}
        direction = tokens.get(prefix.strip())
        if direction is None:
            return None
        assert self.resolved_field is not None
        policy = self.resolved_field.limit_policy
        if direction is LimitTokenDirection.upper and (
            not policy.upper_limit_supported
        ):
            return None
        if direction is LimitTokenDirection.lower and (
            not policy.lower_limit_supported
        ):
            return None
        return direction

    def _resolve_unit(self) -> DocumentObservationAdmissionCode | None:
        assert self.resolved_field is not None
        field = self.resolved_field
        unit_id = self.resolver.unit_id_for(field=field, token=self.raw_unit_token)
        if unit_id is None:
            return DocumentObservationAdmissionCode.document_unit_unresolved
        self.unit_id = unit_id
        return None

    def _derive_candidate_id(self) -> str:
        digest = compute_canonical_payload_hash(
            {
                "document_parse_id": self.context.document_parse_id,
                "locator": self.locator.model_dump(mode="json"),
                "raw_text": self.raw_text,
                "raw_unit": self.raw_unit_token,
                "rule_set": {
                    "id": self.rules.rule_set_id,
                    "version": self.rules.version,
                    "configuration_hash": self.rules.configuration_hash,
                },
            }
        ).removeprefix("sha256:")
        return f"cand.{digest[:24]}"

    def to_raw_candidate(self, *, created_at) -> ScientificDataExtractionCandidate:
        return ScientificDataExtractionCandidate(
            candidate_id=self.candidate_id or "cand.unresolved.pending",
            raw_value=self.raw_text,
            raw_unit=self.raw_unit_token,
            raw_text=self.raw_text,
            field_hint=self.header_context,
            object_hint=self.entity_token,
            research_input_id=str(self.context.research_input_id),
            source_snapshot_id=str(self.context.source_snapshot_id),
            document_parse_id=str(self.context.document_parse_id),
            parse_quality=self.parse_quality,
            locator=self.locator,
            created_at=created_at,
        )

    def to_typed_observation(
        self,
        *,
        context: PersistedDocumentContext,
        snapshot_projection: DataSourceSnapshotProjection,
    ) -> TypedDocumentObservation:
        assert self.resolved_field is not None and self.logical_key is not None
        assert self.unit_id is not None
        return TypedDocumentObservation(
            observation_id=f"obs.{self.candidate_id.removeprefix('cand.')}",
            raw_candidate_id=self.candidate_id,
            research_input_id=context.research_input_id,
            document_parse_id=context.document_parse_id,
            persisted_source_snapshot_id=context.source_snapshot_id,
            pipeline_source_snapshot=snapshot_projection,
            document_locator=self.locator,
            parse_quality=self.parse_quality,
            canonical_field_id=self.resolved_field.field_id,
            crossmatch_logical_key=self.logical_key,
            raw_value=self.raw_text,
            raw_text=self.raw_text,
            parsed_scalar=self.parsed_scalar,
            source_unit=self.unit_id,
            uncertainty_positive_raw=self.positive_error,
            uncertainty_negative_raw=self.negative_error,
            limit_status=self.limit_status,
            null_status=self.null_status,
        )


class _Resolver:
    """Field and unit lookups over the frozen manifest bundle."""

    def __init__(
        self,
        *,
        manifests: ManifestBundle,
        requested_fields: tuple[CanonicalFieldId, ...],
    ) -> None:
        self._fields = tuple(
            field
            for field in manifests.field_manifest.fields
            if field.field_id in set(requested_fields)
        )
        units_by_id = {unit.unit_id: unit for unit in manifests.field_manifest.units}
        self._unit_ids = frozenset(units_by_id)
        self._unit_labels = {
            normalize_document_alias_label(unit.label): unit_id
            for unit_id, unit in units_by_id.items()
        }
        self._unit_symbols = {
            unit.symbol: unit_id for unit_id, unit in units_by_id.items()
        }
        self._quantity_kinds = {
            unit_id: unit.quantity_kind for unit_id, unit in units_by_id.items()
        }
        self._conversion_rule_ids = {
            field.field_id: {
                unit_id: frozenset(
                    alias.conversion_rule_id
                    for alias in field.source_aliases
                    if alias.source_unit == unit_id
                )
                for unit_id in self._unit_ids
            }
            for field in self._fields
        }
        self._alias_index: dict[str, list[FieldDefinition]] = {}
        for field in self._fields:
            keys = {normalize_document_alias_label(field.field_id)}
            keys.update(
                normalize_document_alias_label(alias.alias)
                for alias in field.document_aliases
            )
            for key in keys:
                self._alias_index.setdefault(key, []).append(field)

    def fields_for_label(self, label: str) -> list[FieldDefinition]:
        normalized = normalize_document_alias_label(label)
        stripped = re.sub(r"\s*[\[(].*?[\])]\s*$", "", normalized).strip()
        for candidate in (normalized, stripped):
            matched = self._alias_index.get(candidate)
            if matched:
                return sorted(matched, key=lambda item: item.field_id)
        return []

    def split_header_unit(self, label: str) -> tuple[str, str | None]:
        """Return (base label, bracketed unit token) for one header cell."""

        match = re.search(r"[\[(](.+)[\])]\s*$", label.strip())
        if match is None:
            return label.strip(), None
        return label[: match.start()].strip(), match.group(1).strip()

    def unit_id_for(self, *, field: FieldDefinition, token: str | None) -> str | None:
        if token is None or token == "":
            canonical_kind = self._quantity_kinds[field.canonical_unit]
            return "none" if canonical_kind.value == "none" else None
        cleaned = token.strip()
        if cleaned in self._unit_ids:
            unit_id = cleaned
        else:
            unit_id = self._unit_labels.get(normalize_document_alias_label(cleaned))
            if unit_id is None:
                unit_id = self._unit_symbols.get(cleaned)
        if unit_id is None:
            return None
        if self._quantity_kinds[unit_id] != self._quantity_kinds[field.canonical_unit]:
            return None
        if len(self._conversion_rule_ids[field.field_id][unit_id]) != 1:
            return None
        return unit_id


class _EntityIndex:
    """Exact unique entity lookup over frozen crossmatch identity rows."""

    _NORMALIZERS = (
        normalize_name,
        normalize_toi_id,
        normalize_tic_id,
        normalize_gaia_dr3_id,
    )

    def __init__(self, *, crossmatch: CrossmatchResult) -> None:
        candidates = {item.candidate_id: item for item in crossmatch.candidates}
        self._keys_by_token: dict[str, set[str]] = {}
        self._objects_by_token: dict[str, set[str]] = {}
        for record in crossmatch.records:
            record_key = compute_crossmatch_record_logical_key(record)
            for candidate_id in self._member_ids(record):
                candidate = candidates.get(candidate_id)
                if candidate is None:
                    continue
                object_type = (
                    "star" if candidate.entity_level.value == "host_star" else "planet"
                )
                for value in candidate.identity_values:
                    self._keys_by_token.setdefault(value.normalized_value, set()).add(
                        record_key
                    )
                    self._objects_by_token.setdefault(
                        value.normalized_value, set()
                    ).add(object_type)

    @staticmethod
    def _member_ids(record: CrossmatchRecord) -> tuple[str, ...]:
        if isinstance(record, UnpairedRecord):
            return (record.candidate_id,)
        return tuple(sorted((*record.left_candidate_ids, *record.right_candidate_ids)))

    def _token_forms(self, token: str) -> set[str]:
        forms = {token.strip()}
        for normalizer in self._NORMALIZERS:
            try:
                forms.add(normalizer(token))
            except ValueError:
                continue
        return forms

    def exact_unique_match(
        self, token: str, object_type: str
    ) -> tuple[str | None, str]:
        """Return ``(logical_key, status)`` with status matched/unresolved/ambiguous."""

        keys: set[str] = set()
        objects: set[str] = set()
        for form in self._token_forms(token):
            keys.update(self._keys_by_token.get(form, ()))
            objects.update(self._objects_by_token.get(form, ()))
        if object_type not in objects or not keys:
            return None, "unresolved"
        if len(keys) > 1:
            return None, "ambiguous"
        return next(iter(keys)), "matched"

    def object_type_for_token(self, token: str) -> str | None:
        objects: set[str] = set()
        for form in self._token_forms(token):
            objects.update(self._objects_by_token.get(form, ()))
        if len(objects) == 1:
            return next(iter(objects))
        return None


@dataclass(frozen=True, slots=True)
class _TableColumn:
    """Resolved semantic facts for one usable table header column."""

    column_index: int
    label: str
    unit_token: str | None
    field_candidates: tuple[FieldDefinition, ...]
    header_quality: DocumentParseQuality


@dataclass(frozen=True, slots=True)
class _TableLayout:
    """Immutable header layout used to derive table observations."""

    header_index: int
    entity_column: int
    columns: tuple[_TableColumn, ...]


class _Extractor:
    """Canonical table/text readers producing raw drafts."""

    def __init__(
        self,
        *,
        context: PersistedDocumentContext,
        resolver: _Resolver,
        entities: _EntityIndex,
        rules: DocumentObservationRuleSet,
    ) -> None:
        self._context = context
        self._resolver = resolver
        self._entities = entities
        self._rules = rules

    def table_drafts(self, table: DocumentTable) -> list[_Draft]:
        if not table.rows:
            return []
        layout = self._table_layout(table)
        if layout is None:
            return []
        columns = {item.column_index: item for item in layout.columns}
        entity_column = layout.entity_column
        entity_header = columns[entity_column]
        drafts: list[_Draft] = []
        for body_row in table.rows[layout.header_index + 1 :]:
            entity_cell = next(
                (cell for cell in body_row if cell.column_index == entity_column),
                None,
            )
            if entity_cell is None or entity_cell.quality is (
                DocumentParseQuality.unsupported
            ):
                continue
            entity_token = (entity_cell.text or "").strip()
            if entity_token == "":
                continue
            for cell in body_row:
                column = columns.get(cell.column_index)
                if column is None or (cell.column_index == entity_column):
                    continue
                if cell.quality is DocumentParseQuality.unsupported:
                    continue
                text = (cell.text or "").strip()
                if text == "":
                    continue
                quality = _observation_region_quality(
                    table.quality,
                    entity_header.header_quality,
                    column.header_quality,
                    entity_cell.quality,
                    cell.quality,
                )
                draft = _Draft(
                    context=self._context,
                    resolver=self._resolver,
                    entities=self._entities,
                    rules=self._rules,
                    locator=DocumentLocator(
                        page_index=table.page_index,
                        block_id=table.block_id,
                        bbox=cell.bbox,
                        table_id=table.table_id,
                        cell_id=cell.cell_id,
                    ),
                    parse_quality=quality,
                    raw_text=text,
                    header_context=column.label,
                    header_unit_token=column.unit_token,
                    entity_token=entity_token,
                    row_context=((f"col:{entity_column}", entity_token),),
                    field_candidates=column.field_candidates,
                )
                drafts.append(draft)
        return drafts

    def _table_layout(self, table: DocumentTable) -> _TableLayout | None:
        for index, row in enumerate(table.rows):
            columns: list[_TableColumn] = []
            entity_column: int | None = None
            for cell in row:
                label = (cell.text or "").strip()
                if (
                    not cell.is_header
                    or label == ""
                    or cell.quality is DocumentParseQuality.unsupported
                ):
                    continue
                base, unit_token = self._resolver.split_header_unit(label)
                matches = tuple(
                    sorted(
                        self._resolver.fields_for_label(base), key=lambda f: f.field_id
                    )
                )
                columns.append(
                    _TableColumn(
                        column_index=cell.column_index,
                        label=label,
                        unit_token=unit_token,
                        field_candidates=matches,
                        header_quality=cell.quality,
                    )
                )
                if any(field.object_identity_key for field in matches):
                    entity_column = cell.column_index
            if entity_column is not None:
                return _TableLayout(
                    header_index=index,
                    entity_column=entity_column,
                    columns=tuple(columns),
                )
        return None

    def text_drafts(self, parse: DocumentParseCandidate) -> list[_Draft]:
        patterns = self._rules.declared_text_patterns
        if not patterns:
            return []
        drafts: list[_Draft] = []
        for pattern in patterns:
            compiled = re.compile(pattern.pattern)
            for block in parse.blocks:
                if block.kind.value not in ("paragraph", "list"):
                    continue
                if block.quality is DocumentParseQuality.unsupported:
                    continue
                if block.text is None:
                    continue
                for match in compiled.finditer(block.text):
                    groups = match.groupdict()
                    if any(
                        groups.get(name) in (None, "")
                        for name in ("field", "value", "entity")
                    ):
                        continue
                    quality = (
                        DocumentParseQuality.accepted
                        if block.quality is DocumentParseQuality.accepted
                        else DocumentParseQuality.partial
                    )
                    start, end = match.span()
                    drafts.append(
                        _Draft(
                            context=self._context,
                            resolver=self._resolver,
                            entities=self._entities,
                            rules=self._rules,
                            locator=DocumentLocator(
                                page_index=block.page_index,
                                block_id=block.block_id,
                                bbox=block.bbox,
                                reading_order=block.reading_order,
                                text_span=TextSpan(start=start, end=end),
                            ),
                            parse_quality=quality,
                            raw_text=groups["value"].strip(),
                            header_context=groups["field"].strip(),
                            header_unit_token=(groups.get("unit") or "").strip()
                            or None,
                            entity_token=groups["entity"].strip(),
                            row_context=(("pattern", pattern.pattern_id),),
                        )
                    )
        return drafts


__all__ = [
    "DocumentObservationError",
    "DocumentObservationOutcome",
    "PersistedDocumentContext",
    "RawExtractionBatch",
    "extract_document_observations",
]
