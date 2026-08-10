"""Process-local publication authority for Versioned Evidence Graph candidates.

The public candidate is intentionally round-trippable, while the admission
snapshot, seal, and authority registry are not serialized.
``services.graph_pipeline.pipeline.GraphPipeline`` consumes
``_bind_graph_pipeline_authority`` once at import time and define ``admit``
with a private keyword-only ``_authority_minter`` parameter.  The binder then
removes itself, and only the exact active ``GraphPipeline.admit`` frame can
mint publication authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import sys
from threading import RLock
from typing import Any, NamedTuple
import weakref

from ._hashing import compute_canonical_payload_hash


@dataclass(frozen=True, slots=True, weakref_slot=True)
class GraphAdmissionSnapshot:
    input_json: str
    input_hash: str
    scientific_hash: str
    layout_hash: str
    report_hash: str
    context_hash: str
    admission_commitment_hash: str


@dataclass(frozen=True, slots=True, weakref_slot=True)
class GraphPublicationSeal:
    object_id: int
    candidate_module: str
    candidate_class: str
    candidate_kind: str
    schema_version: str
    input_hash: str
    scientific_hash: str
    layout_hash: str
    report_hash: str
    output_hash: str
    public_payload_hash: str
    context_hash: str
    admission_commitment_hash: str


class _GraphPublicationAuthority(NamedTuple):
    object_id: int
    candidate_ref: weakref.ReferenceType[Any]
    seal_ref: weakref.ReferenceType[GraphPublicationSeal]
    context_ref: weakref.ReferenceType[GraphAdmissionSnapshot]
    candidate_module: str
    candidate_class: str
    candidate_kind: str
    schema_version: str
    input_hash: str
    scientific_hash: str
    layout_hash: str
    report_hash: str
    output_hash: str
    public_payload_hash: str
    context_input_json: str
    context_hash: str
    admission_commitment_hash: str


def _context_hash(snapshot: GraphAdmissionSnapshot) -> str:
    return compute_canonical_payload_hash(
        {
            "input_json": snapshot.input_json,
            "input_hash": snapshot.input_hash,
            "scientific_hash": snapshot.scientific_hash,
            "layout_hash": snapshot.layout_hash,
            "report_hash": snapshot.report_hash,
        }
    )


def _commitment_hash(
    value: Any,
    *,
    public_payload_hash: str,
    context_hash: str,
) -> str:
    return compute_canonical_payload_hash(
        {
            "candidate_module": value.__class__.__module__,
            "candidate_class": value.__class__.__name__,
            "candidate_kind": value.kind,
            "schema_version": value.schema_version,
            "input_hash": value.input_hash,
            "scientific_hash": value.scientific_hash,
            "layout_hash": value.layout_hash,
            "report_hash": value.report_hash,
            "output_hash": value.output_hash,
            "public_payload_hash": public_payload_hash,
            "context_hash": context_hash,
        }
    )


def build_graph_admission_snapshot(
    value: Any,
    *,
    input_json: str,
    public_payload_hash: str,
) -> GraphAdmissionSnapshot:
    """Build the single canonical context/commitment snapshot used by Versioned Evidence Graph."""

    if not isinstance(input_json, str) or not input_json:
        raise ValueError("Graph admission input_json must be nonempty")
    provisional = GraphAdmissionSnapshot(
        input_json=input_json,
        input_hash=value.input_hash,
        scientific_hash=value.scientific_hash,
        layout_hash=value.layout_hash,
        report_hash=value.report_hash,
        context_hash="",
        admission_commitment_hash="",
    )
    context_hash = _context_hash(provisional)
    commitment_hash = _commitment_hash(
        value,
        public_payload_hash=public_payload_hash,
        context_hash=context_hash,
    )
    return GraphAdmissionSnapshot(
        input_json=input_json,
        input_hash=value.input_hash,
        scientific_hash=value.scientific_hash,
        layout_hash=value.layout_hash,
        report_hash=value.report_hash,
        context_hash=context_hash,
        admission_commitment_hash=commitment_hash,
    )


def _build_graph_publication_authority() -> tuple[Any, Any]:
    authority_lock = RLock()
    publication_authorities: tuple[_GraphPublicationAuthority, ...] = ()
    authorized_admit_code: Any = None
    minter_available = True

    def load_authority(object_id: int) -> _GraphPublicationAuthority | None:
        with authority_lock:
            return next(
                (
                    item
                    for item in publication_authorities
                    if item.object_id == object_id
                ),
                None,
            )

    def register_authority(
        object_id: int,
        authority: _GraphPublicationAuthority,
    ) -> None:
        nonlocal publication_authorities
        if sys._getframe(1).f_code is not mint.__code__:
            raise RuntimeError("Graph authority registration is mint-private")
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
                item
                for item in publication_authorities
                if not (
                    item.object_id == object_id
                    and item.candidate_ref is reference
                )
            )

    def mint(
        value: Any,
        snapshot: GraphAdmissionSnapshot,
        *,
        public_payload_hash: str,
    ) -> Any:
        caller = sys._getframe(1)
        if (
            caller.f_code is not authorized_admit_code
            or caller.f_locals.get("candidate") is not value
        ):
            raise RuntimeError(
                "Graph publication authority requires the active GraphPipeline admission"
            )
        if (
            value.__class__.__module__ != "app.schemas.graph_artifact"
            or value.__class__.__name__ != "GraphArtifactCandidate"
        ):
            raise TypeError("Graph publication authority requires the exact candidate class")
        expected_context_hash = _context_hash(snapshot)
        expected_commitment_hash = _commitment_hash(
            value,
            public_payload_hash=public_payload_hash,
            context_hash=expected_context_hash,
        )
        if (
            snapshot.input_hash != value.input_hash
            or snapshot.scientific_hash != value.scientific_hash
            or snapshot.layout_hash != value.layout_hash
            or snapshot.report_hash != value.report_hash
            or snapshot.context_hash != expected_context_hash
            or snapshot.admission_commitment_hash != expected_commitment_hash
        ):
            raise ValueError("Graph admission commitment does not match candidate")

        seal = GraphPublicationSeal(
            object_id=id(value),
            candidate_module=value.__class__.__module__,
            candidate_class=value.__class__.__name__,
            candidate_kind=value.kind,
            schema_version=value.schema_version,
            input_hash=value.input_hash,
            scientific_hash=value.scientific_hash,
            layout_hash=value.layout_hash,
            report_hash=value.report_hash,
            output_hash=value.output_hash,
            public_payload_hash=public_payload_hash,
            context_hash=snapshot.context_hash,
            admission_commitment_hash=snapshot.admission_commitment_hash,
        )
        object_id = id(value)

        def revoke(reference: weakref.ReferenceType[Any]) -> None:
            revoke_authority(object_id, reference)

        candidate_ref = weakref.ref(value, revoke)
        authority = _GraphPublicationAuthority(
            object_id=object_id,
            candidate_ref=candidate_ref,
            seal_ref=weakref.ref(seal),
            context_ref=weakref.ref(snapshot),
            candidate_module=seal.candidate_module,
            candidate_class=seal.candidate_class,
            candidate_kind=seal.candidate_kind,
            schema_version=seal.schema_version,
            input_hash=seal.input_hash,
            scientific_hash=seal.scientific_hash,
            layout_hash=seal.layout_hash,
            report_hash=seal.report_hash,
            output_hash=seal.output_hash,
            public_payload_hash=seal.public_payload_hash,
            context_input_json=snapshot.input_json,
            context_hash=seal.context_hash,
            admission_commitment_hash=seal.admission_commitment_hash,
        )
        register_authority(object_id, authority)
        object.__setattr__(value, "_artifact_publication_context", snapshot)
        object.__setattr__(value, "_artifact_publication_seal", seal)
        return value

    def verify(
        value: Any,
        seal: GraphPublicationSeal | None,
        context: GraphAdmissionSnapshot | None,
        *,
        public_payload_hash: str,
    ) -> bool:
        if (
            value.__class__.__module__ != "app.schemas.graph_artifact"
            or value.__class__.__name__ != "GraphArtifactCandidate"
            or not isinstance(seal, GraphPublicationSeal)
            or not isinstance(context, GraphAdmissionSnapshot)
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
        expected_context_hash = _context_hash(context)
        expected_commitment_hash = _commitment_hash(
            value,
            public_payload_hash=public_payload_hash,
            context_hash=expected_context_hash,
        )
        return (
            authority.object_id == id(value)
            and authority.candidate_module == value.__class__.__module__
            and authority.candidate_class == value.__class__.__name__
            and authority.candidate_kind == value.kind == seal.candidate_kind
            and authority.schema_version == value.schema_version == seal.schema_version
            and authority.input_hash == value.input_hash == seal.input_hash
            and authority.scientific_hash
            == value.scientific_hash
            == seal.scientific_hash
            and authority.layout_hash == value.layout_hash == seal.layout_hash
            and authority.report_hash == value.report_hash == seal.report_hash
            and authority.output_hash == value.output_hash == seal.output_hash
            and authority.public_payload_hash
            == public_payload_hash
            == seal.public_payload_hash
            and authority.context_input_json == context.input_json
            and authority.context_hash
            == context.context_hash
            == seal.context_hash
            == expected_context_hash
            and authority.admission_commitment_hash
            == context.admission_commitment_hash
            == seal.admission_commitment_hash
            == expected_commitment_hash
            and context.input_hash == value.input_hash
            and context.scientific_hash == value.scientific_hash
            and context.layout_hash == value.layout_hash
            and context.report_hash == value.report_hash
            and seal.object_id == id(value)
        )

    def bind_graph_pipeline_authority(pipeline_class: Any) -> Any:
        """Bind once to the exact GraphPipeline owner and wrap ``admit``."""

        nonlocal authorized_admit_code, minter_available
        if not minter_available:
            raise RuntimeError("Graph publication authority was already bound")
        owner_module = sys.modules.get("services.graph_pipeline.pipeline")
        if (
            pipeline_class.__module__ != "services.graph_pipeline.pipeline"
            or pipeline_class.__name__ != "GraphPipeline"
            or owner_module is None
            or getattr(owner_module, "GraphPipeline", None) is not pipeline_class
        ):
            raise RuntimeError(
                "Graph publication authority requires services.graph_pipeline.pipeline.GraphPipeline"
            )
        original_admit = pipeline_class.admit
        authorized_admit_code = original_admit.__code__
        authority_minter = mint
        minter_available = False
        globals().pop("_bind_graph_pipeline_authority", None)

        def admitted(pipeline: Any, *args: Any, **kwargs: Any) -> Any:
            if "_authority_minter" in kwargs:
                raise TypeError("Graph publication authority is Pipeline-private")
            return original_admit(
                pipeline,
                *args,
                _authority_minter=authority_minter,
                **kwargs,
            )

        admitted.__name__ = "admit"
        admitted.__qualname__ = "GraphPipeline.admit"
        admitted.__doc__ = original_admit.__doc__
        pipeline_class.admit = admitted
        return pipeline_class

    return bind_graph_pipeline_authority, verify


(
    _bind_graph_pipeline_authority,
    graph_artifact_candidate_is_sealed,
) = _build_graph_publication_authority()
del _build_graph_publication_authority


__all__ = [
    "GraphAdmissionSnapshot",
    "GraphPublicationSeal",
    "build_graph_admission_snapshot",
    "graph_artifact_candidate_is_sealed",
]
