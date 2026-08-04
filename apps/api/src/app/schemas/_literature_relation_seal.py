"""Process-local publication commitment for D-08 Relation candidates.

The admission snapshot and seal are intentionally absent from JSON Schema and
serialization. Reconstructing a valid public Pydantic payload therefore never
reconstructs publication authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import sys
from threading import RLock
from typing import Any, NamedTuple
import weakref

from ._hashing import compute_canonical_payload_hash


@dataclass(frozen=True, slots=True, weakref_slot=True)
class LiteratureRelationAdmissionSnapshot:
    input_json: str
    input_hash: str
    context_hash: str
    admission_commitment_hash: str


@dataclass(frozen=True, slots=True, weakref_slot=True)
class LiteratureRelationPublicationSeal:
    object_id: int
    candidate_kind: str
    schema_version: str
    input_hash: str
    output_hash: str
    public_payload_hash: str
    context_hash: str
    admission_commitment_hash: str


class _LiteratureRelationPublicationAuthority(NamedTuple):
    """Immutable registry record for one exact in-memory candidate.

    The verifier can expose this snapshot through normal Python introspection
    without exposing a mutable trust store. Weak references preserve exact
    object identity without keeping candidates, seals, or contexts alive.
    """

    object_id: int
    candidate_ref: weakref.ReferenceType[Any]
    seal_ref: weakref.ReferenceType[LiteratureRelationPublicationSeal]
    context_ref: weakref.ReferenceType[LiteratureRelationAdmissionSnapshot]
    candidate_kind: str
    schema_version: str
    input_hash: str
    output_hash: str
    public_payload_hash: str
    context_input_json: str
    context_hash: str
    admission_commitment_hash: str


def _build_publication_authority() -> tuple[Any, Any]:
    """Create one process-local authority and a single-use minter handoff.

    The registry and mint callable only exist in closures. The Pipeline consumes
    the handoff while importing and the handoff removes itself from this module,
    leaving no callable mint or mutable registry for another module to import.
    """

    authority_lock = RLock()
    publication_authorities: tuple[_LiteratureRelationPublicationAuthority, ...] = ()
    authorized_admit_code: Any = None

    def load_authority(object_id: int) -> _LiteratureRelationPublicationAuthority | None:
        with authority_lock:
            return next(
                (
                    authority
                    for authority in publication_authorities
                    if authority.object_id == object_id
                ),
                None,
            )

    def register_authority(
        object_id: int,
        authority: _LiteratureRelationPublicationAuthority,
    ) -> None:
        nonlocal publication_authorities
        if sys._getframe(1).f_code is not mint.__code__:
            raise RuntimeError("Relation authority registration is mint-private")
        with authority_lock:
            publication_authorities = tuple(
                item for item in publication_authorities if item.object_id != object_id
            ) + (authority,)

    def revoke_authority(
        object_id: int,
        reference: weakref.ReferenceType[Any],
    ) -> None:
        nonlocal publication_authorities
        with authority_lock:
            publication_authorities = tuple(
                authority
                for authority in publication_authorities
                if not (
                    authority.object_id == object_id
                    and authority.candidate_ref is reference
                )
            )

    def mint(
        value: Any,
        snapshot: LiteratureRelationAdmissionSnapshot,
        *,
        public_payload_hash: str,
    ) -> Any:
        caller = sys._getframe(1)
        if (
            caller.f_code is not authorized_admit_code
            or caller.f_locals.get("candidate") is not value
        ):
            raise RuntimeError(
                "Relation publication authority requires the active Pipeline admission"
            )
        expected_context_hash = compute_canonical_payload_hash(
            {"input_json": snapshot.input_json, "input_hash": snapshot.input_hash}
        )
        expected_commitment_hash = compute_canonical_payload_hash(
            {
                "candidate_kind": value.kind,
                "schema_version": value.schema_version,
                "input_hash": value.input_hash,
                "output_hash": value.output_hash,
                "public_payload_hash": public_payload_hash,
                "context_hash": expected_context_hash,
            }
        )
        if (
            snapshot.input_hash != value.input_hash
            or snapshot.context_hash != expected_context_hash
            or snapshot.admission_commitment_hash != expected_commitment_hash
        ):
            raise ValueError("Relation admission commitment does not match candidate")
        seal = LiteratureRelationPublicationSeal(
            object_id=id(value),
            candidate_kind=value.kind,
            schema_version=value.schema_version,
            input_hash=value.input_hash,
            output_hash=value.output_hash,
            public_payload_hash=public_payload_hash,
            context_hash=snapshot.context_hash,
            admission_commitment_hash=snapshot.admission_commitment_hash,
        )
        object_id = id(value)

        def revoke(reference: weakref.ReferenceType[Any]) -> None:
            revoke_authority(object_id, reference)

        candidate_ref = weakref.ref(value, revoke)
        authority = _LiteratureRelationPublicationAuthority(
            object_id=object_id,
            candidate_ref=candidate_ref,
            seal_ref=weakref.ref(seal),
            context_ref=weakref.ref(snapshot),
            candidate_kind=seal.candidate_kind,
            schema_version=seal.schema_version,
            input_hash=seal.input_hash,
            output_hash=seal.output_hash,
            public_payload_hash=seal.public_payload_hash,
            context_input_json=snapshot.input_json,
            context_hash=snapshot.context_hash,
            admission_commitment_hash=snapshot.admission_commitment_hash,
        )
        register_authority(object_id, authority)
        object.__setattr__(value, "_artifact_publication_context", snapshot)
        object.__setattr__(value, "_artifact_publication_seal", seal)
        return value

    def verify(
        value: Any,
        seal: LiteratureRelationPublicationSeal | None,
        context: LiteratureRelationAdmissionSnapshot | None,
        *,
        public_payload_hash: str,
    ) -> bool:
        if not isinstance(seal, LiteratureRelationPublicationSeal) or not isinstance(
            context, LiteratureRelationAdmissionSnapshot
        ):
            return False
        authority = load_authority(id(value))
        if (
            authority is None
            or authority.candidate_ref() is not value
            or authority.seal_ref() is not seal
            or authority.context_ref() is not context
        ):
            return False
        expected_context_hash = compute_canonical_payload_hash(
            {"input_json": context.input_json, "input_hash": context.input_hash}
        )
        expected_commitment_hash = compute_canonical_payload_hash(
            {
                "candidate_kind": getattr(value, "kind", None),
                "schema_version": getattr(value, "schema_version", None),
                "input_hash": getattr(value, "input_hash", None),
                "output_hash": getattr(value, "output_hash", None),
                "public_payload_hash": public_payload_hash,
                "context_hash": expected_context_hash,
            }
        )
        return (
            authority.object_id == id(value)
            and authority.candidate_kind == seal.candidate_kind
            and authority.schema_version == seal.schema_version
            and authority.input_hash == seal.input_hash
            and authority.output_hash == seal.output_hash
            and authority.public_payload_hash == seal.public_payload_hash
            and authority.context_input_json == context.input_json
            and authority.context_hash == context.context_hash
            and authority.admission_commitment_hash
            == context.admission_commitment_hash
            and seal.object_id == id(value)
            and seal.candidate_kind == getattr(value, "kind", None)
            and seal.schema_version == getattr(value, "schema_version", None)
            and seal.input_hash == getattr(value, "input_hash", None)
            and seal.output_hash == getattr(value, "output_hash", None)
            and context.input_hash == seal.input_hash
            and context.context_hash == expected_context_hash
            and context.admission_commitment_hash == expected_commitment_hash
            and context.context_hash == seal.context_hash
            and context.admission_commitment_hash
            == seal.admission_commitment_hash
            and seal.public_payload_hash == public_payload_hash
        )

    minter = mint

    def bind_pipeline_authority(pipeline_class: Any) -> Any:
        nonlocal authorized_admit_code, minter
        if minter is None:
            raise RuntimeError("Relation publication authority was already bound")
        owner_module = sys.modules.get("services.paper_pipeline.relation")
        if (
            pipeline_class.__module__ != "services.paper_pipeline.relation"
            or pipeline_class.__name__ != "LiteratureRelationPipeline"
            or owner_module is None
            or getattr(owner_module, "LiteratureRelationPipeline", None)
            is not pipeline_class
        ):
            raise RuntimeError(
                "Relation publication authority requires its exact Pipeline owner"
            )
        original_admit = pipeline_class.admit
        authorized_admit_code = original_admit.__code__
        authority_minter = minter
        minter = None
        globals().pop("_bind_literature_relation_pipeline_authority", None)

        def admitted(pipeline: Any, *args: Any, **kwargs: Any) -> Any:
            if "_authority_minter" in kwargs:
                raise TypeError("Relation publication authority is Pipeline-private")
            return original_admit(
                pipeline,
                *args,
                _authority_minter=authority_minter,
                **kwargs,
            )

        admitted.__name__ = "admit"
        admitted.__qualname__ = "LiteratureRelationPipeline.admit"
        admitted.__doc__ = original_admit.__doc__
        pipeline_class.admit = admitted
        return pipeline_class

    return bind_pipeline_authority, verify


(
    _bind_literature_relation_pipeline_authority,
    literature_relations_candidate_is_sealed,
) = _build_publication_authority()
del _build_publication_authority


__all__ = [
    "LiteratureRelationAdmissionSnapshot",
    "LiteratureRelationPublicationSeal",
    "literature_relations_candidate_is_sealed",
]
