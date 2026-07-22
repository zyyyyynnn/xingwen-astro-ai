"""M1 required-operation parity between the contract and the runtime.

The contract-only OpenAPI (`app.contracts.v2`) is the authoritative operation
surface. This test asserts that the mounted runtime implements every M1
required operation with the *same* HTTP method, path and operationId. It does
not force any future ``/api/v2`` target to exist early; it only checks the M1
required set (which currently equals the full frozen 24-operation contract).
"""

from __future__ import annotations

from app.contracts.v2 import create_v2_contract_app
from app.main import create_app


_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _operations(document: dict[str, object]) -> set[tuple[str, str, str]]:
    surface: set[tuple[str, str, str]] = set()
    paths = document["paths"]
    assert isinstance(paths, dict)
    for path, item in paths.items():
        assert isinstance(item, dict)
        for method, operation in item.items():
            if method not in _HTTP_METHODS:
                continue
            assert isinstance(operation, dict)
            surface.add((method, path, operation["operationId"]))
    return surface


def test_runtime_implements_every_m1_required_contract_operation() -> None:
    contract = _operations(create_v2_contract_app().openapi())
    runtime = _operations(create_app().openapi())

    # The M1 required set is the full frozen contract surface.
    missing = sorted(contract - runtime)
    assert not missing, f"runtime is missing required operations: {missing}"


def test_runtime_operation_ids_are_unique() -> None:
    document = create_app().openapi()
    operation_ids = [
        operation["operationId"]
        for item in document["paths"].values()
        for method, operation in item.items()
        if method in _HTTP_METHODS
    ]
    assert len(operation_ids) == len(set(operation_ids))


def test_required_operations_match_method_and_path_exactly() -> None:
    contract = _operations(create_v2_contract_app().openapi())
    runtime_by_op = {
        op_id: (method, path)
        for method, path, op_id in _operations(create_app().openapi())
    }
    mismatched: list[str] = []
    for method, path, op_id in sorted(contract):
        if runtime_by_op.get(op_id) != (method, path):
            mismatched.append(
                f"{op_id}: contract={method} {path} runtime={runtime_by_op.get(op_id)}"
            )
    assert not mismatched, "; ".join(mismatched)
