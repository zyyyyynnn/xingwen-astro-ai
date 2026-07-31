"""Manifest-driven projection of raw source records into entity candidates."""

from __future__ import annotations

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.crossmatch import (
    CanonicalIdentityValue,
    CrossmatchRuleSet,
    CrossmatchSide,
    EntityCandidate,
    EntityLevel,
    EvidenceLocator,
    SkyCoordinate,
    SourceRecordReference,
    compute_crossmatch_content_hash,
)
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.manifest import ManifestBundle
from app.schemas.source_acquisition import RawDataSourceRecord

from .errors import CrossmatchError
from .identity import (
    normalize_gaia_dr3_id,
    normalize_name,
    normalize_sky_coordinate,
    normalize_tic_id,
    normalize_toi_id,
)


_TOI_SOURCE_ID = "nasa_exoplanet_archive.toi"
_PS_SOURCE_ID = "nasa_exoplanet_archive.ps"


def normalize_source_candidates(
    records: tuple[RawDataSourceRecord, ...],
    *,
    side: CrossmatchSide,
    snapshot: SourceSnapshotRecord,
    bundle: ManifestBundle,
    rule_set: CrossmatchRuleSet,
) -> tuple[EntityCandidate, ...]:
    normalized: list[EntityCandidate] = []
    for record in sorted(records, key=lambda value: value.row_key):
        host = _host_candidate(
            record,
            side=side,
            snapshot=snapshot,
            bundle=bundle,
            rule_set=rule_set,
        )
        if host is not None:
            normalized.append(host)
        planet = _planet_candidate(
            record,
            side=side,
            snapshot=snapshot,
            bundle=bundle,
            rule_set=rule_set,
        )
        if planet is not None:
            normalized.append(planet)
    return tuple(normalized)


def _host_candidate(
    record: RawDataSourceRecord,
    *,
    side: CrossmatchSide,
    snapshot: SourceSnapshotRecord,
    bundle: ManifestBundle,
    rule_set: CrossmatchRuleSet,
) -> EntityCandidate | None:
    values: list[CanonicalIdentityValue] = []
    for field_id, normalizer, normalization_rule_version in (
        (
            "star.tic_id",
            normalize_tic_id,
            rule_set.identifier_policy_version,
        ),
        (
            "star.gaia_dr3_id",
            normalize_gaia_dr3_id,
            rule_set.identifier_policy_version,
        ),
        ("star.name", normalize_name, rule_set.name_policy_version),
    ):
        raw_field = _raw_field(bundle, record.source_id, field_id)
        if raw_field is None:
            continue
        raw_value = record.payload.get(raw_field)
        if raw_value is None or raw_value == "":
            continue
        try:
            normalized = normalizer(raw_value)
        except ValueError as error:
            raise CrossmatchError(
                "CROSSMATCH_INVALID_IDENTIFIER",
                f"invalid {field_id}: {error}",
            ) from None
        values.append(
            _identity_value(
                field_id,
                normalized,
                record=record,
                side=side,
                snapshot=snapshot,
                raw_field=raw_field,
                normalization_rule_version=normalization_rule_version,
            )
        )

    coordinate = _coordinate(record, bundle)
    if coordinate is not None:
        for field_id, normalized in (
            (
                "system.right_ascension",
                _format_float(coordinate.right_ascension),
            ),
            ("system.declination", _format_float(coordinate.declination)),
        ):
            raw_field = _required_raw_field(bundle, record.source_id, field_id)
            values.append(
                _identity_value(
                    field_id,
                    normalized,
                    record=record,
                    side=side,
                    snapshot=snapshot,
                    raw_field=raw_field,
                    normalization_rule_version=(
                        rule_set.coordinate_policy_version
                    ),
                )
            )
    if not values:
        return None
    return _candidate(
        record,
        side=side,
        entity_level=EntityLevel.host_star,
        snapshot=snapshot,
        identity_values=tuple(values),
        coordinate=coordinate,
    )


def _planet_candidate(
    record: RawDataSourceRecord,
    *,
    side: CrossmatchSide,
    snapshot: SourceSnapshotRecord,
    bundle: ManifestBundle,
    rule_set: CrossmatchRuleSet,
) -> EntityCandidate | None:
    if record.source_id == _TOI_SOURCE_ID:
        field_id = "planet.toi_id"
        entity_level = EntityLevel.planet_candidate
        normalizer = normalize_toi_id
        normalization_rule_version = rule_set.identifier_policy_version
    elif record.source_id == _PS_SOURCE_ID:
        field_id = "planet.name"
        entity_level = EntityLevel.planet_assertion
        normalizer = normalize_name
        normalization_rule_version = rule_set.name_policy_version
    else:
        return None
    raw_field = _required_raw_field(bundle, record.source_id, field_id)
    raw_value = record.payload.get(raw_field)
    if raw_value is None or raw_value == "":
        return None
    try:
        normalized = normalizer(raw_value)
    except ValueError as error:
        raise CrossmatchError(
            "CROSSMATCH_INVALID_IDENTIFIER",
            f"invalid {field_id}: {error}",
        ) from None
    value = _identity_value(
        field_id,
        normalized,
        record=record,
        side=side,
        snapshot=snapshot,
        raw_field=raw_field,
        normalization_rule_version=normalization_rule_version,
    )
    return _candidate(
        record,
        side=side,
        entity_level=entity_level,
        snapshot=snapshot,
        identity_values=(value,),
        coordinate=None,
    )


def _coordinate(
    record: RawDataSourceRecord,
    bundle: ManifestBundle,
) -> SkyCoordinate | None:
    ra_field = _raw_field(
        bundle,
        record.source_id,
        "system.right_ascension",
    )
    dec_field = _raw_field(
        bundle,
        record.source_id,
        "system.declination",
    )
    if ra_field is None or dec_field is None:
        return None
    ra = record.payload.get(ra_field)
    dec = record.payload.get(dec_field)
    if ra in (None, "") or dec in (None, ""):
        return None
    try:
        return normalize_sky_coordinate(ra, dec)
    except ValueError as error:
        raise CrossmatchError(
            "CROSSMATCH_INVALID_COORDINATE",
            str(error),
        ) from None


def _identity_value(
    field_id: str,
    normalized_value: str,
    *,
    record: RawDataSourceRecord,
    side: CrossmatchSide,
    snapshot: SourceSnapshotRecord,
    raw_field: str,
    normalization_rule_version: str,
) -> CanonicalIdentityValue:
    return CanonicalIdentityValue(
        field_id=field_id,
        normalized_value=normalized_value,
        normalization_rule_version=normalization_rule_version,
        locator=_locator(
            record,
            side=side,
            snapshot=snapshot,
            raw_field=raw_field,
        ),
    )


def _candidate(
    record: RawDataSourceRecord,
    *,
    side: CrossmatchSide,
    entity_level: EntityLevel,
    snapshot: SourceSnapshotRecord,
    identity_values: tuple[CanonicalIdentityValue, ...],
    coordinate: SkyCoordinate | None,
) -> EntityCandidate:
    identity_payload = {
        "side": side.value,
        "entity_level": entity_level.value,
        "source_id": record.source_id,
        "row_key": record.row_key,
    }
    identity_hash = compute_canonical_payload_hash(identity_payload)
    source_record = SourceRecordReference(
        side=side,
        source_snapshot_id=snapshot.snapshot_id,
        source_snapshot_content_hash=snapshot.content_hash,
        source_id=record.source_id,
        query_hash=snapshot.query_hash,
        row_key=record.row_key,
        record_content_hash=record.content_hash,
        object_type=(
            "star" if entity_level is EntityLevel.host_star else "planet"
        ),
        source_entity_key="|".join(
            f"{field}={value}" for field, value in record.row_key
        ),
    )
    payload = {
        "candidate_id": (
            f"candidate.{identity_hash.removeprefix('sha256:')[:24]}"
        ),
        "side": side,
        "entity_level": entity_level,
        "source_record": source_record.model_dump(mode="json"),
        "identity_values": [
            value.model_dump(mode="json") for value in identity_values
        ],
        "coordinate": (
            coordinate.model_dump(mode="json") if coordinate is not None else None
        ),
    }
    payload["content_hash"] = compute_crossmatch_content_hash(payload)
    return EntityCandidate.model_validate(payload)


def _locator(
    record: RawDataSourceRecord,
    *,
    side: CrossmatchSide,
    snapshot: SourceSnapshotRecord,
    raw_field: str,
) -> EvidenceLocator:
    return EvidenceLocator(
        side=side,
        source_snapshot_id=snapshot.snapshot_id,
        source_id=record.source_id,
        query_hash=snapshot.query_hash,
        row_key=record.row_key,
        raw_field=raw_field,
    )


def _raw_field(
    bundle: ManifestBundle,
    source_id: str,
    field_id: str,
) -> str | None:
    try:
        field = bundle.field_manifest.field_by_id(field_id)
    except KeyError:
        return None
    if not field.crossmatch_key:
        return None
    aliases = field.source_aliases_for(source_id)
    return aliases[0].raw_field if aliases else None


def _required_raw_field(
    bundle: ManifestBundle,
    source_id: str,
    field_id: str,
) -> str:
    raw_field = _raw_field(bundle, source_id, field_id)
    if raw_field is None:
        raise CrossmatchError(
            "CROSSMATCH_SOURCE_CONTRACT_MISMATCH",
            f"Field Manifest does not map {field_id} for {source_id}",
        )
    return raw_field


def _format_float(value: float) -> str:
    return format(value, ".15g")
