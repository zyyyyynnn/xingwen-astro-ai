"""Process-local publication seal state for Versioned Data Artifact candidates.

Nothing in this module is serialized or exported as JSON Schema. A valid
contract round-trip intentionally loses this state and must be admitted again
through the producing process before publication.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_SEAL_TOKEN = object()


@dataclass(frozen=True, slots=True)
class DataArtifactAdmissionSnapshot:
    input_json: str
    input_hash: str
    context_hash: str
    bundle_commitment_hash: str


@dataclass(frozen=True, slots=True)
class DataArtifactPublicationSeal:
    token: object
    object_id: int
    candidate_kind: str
    candidate_id: str
    input_hash: str
    output_hash: str
    public_payload_hash: str
    context_hash: str
    bundle_commitment_hash: str


def seal_data_artifact_candidate(
    value: Any,
    snapshot: DataArtifactAdmissionSnapshot,
    *,
    public_payload_hash: str,
) -> Any:
    seal = DataArtifactPublicationSeal(
        token=_SEAL_TOKEN,
        object_id=id(value),
        candidate_kind=value.kind,
        candidate_id=value.candidate_id,
        input_hash=value.input_hash,
        output_hash=value.output_hash,
        public_payload_hash=public_payload_hash,
        context_hash=snapshot.context_hash,
        bundle_commitment_hash=snapshot.bundle_commitment_hash,
    )
    object.__setattr__(value, "_artifact_publication_context", snapshot)
    object.__setattr__(value, "_artifact_publication_seal", seal)
    return value


def data_artifact_candidate_is_sealed(
    value: Any,
    seal: DataArtifactPublicationSeal | None,
    context: DataArtifactAdmissionSnapshot | None,
    *,
    public_payload_hash: str,
) -> bool:
    if not isinstance(seal, DataArtifactPublicationSeal) or not isinstance(
        context, DataArtifactAdmissionSnapshot
    ):
        return False
    return (
        seal.token is _SEAL_TOKEN
        and seal.object_id == id(value)
        and seal.candidate_kind == getattr(value, "kind", None)
        and seal.candidate_id == getattr(value, "candidate_id", None)
        and seal.input_hash == getattr(value, "input_hash", None)
        and seal.output_hash == getattr(value, "output_hash", None)
        and context.input_hash == seal.input_hash
        and context.context_hash == seal.context_hash
        and context.bundle_commitment_hash == seal.bundle_commitment_hash
        and seal.public_payload_hash == public_payload_hash
    )


__all__ = [
    "DataArtifactAdmissionSnapshot",
    "DataArtifactPublicationSeal",
    "data_artifact_candidate_is_sealed",
    "seal_data_artifact_candidate",
]
