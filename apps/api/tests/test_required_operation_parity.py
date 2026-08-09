"""Required-operation parity between the contract and the runtime.

The contract-only OpenAPI (`app.contracts.core`) is the authoritative operation
surface. This test asserts that the mounted runtime implements every required
operation with the *same* HTTP method, path and operationId. It does not
require an unavailable ``/api`` target; it only checks the declared
required set (which currently equals the full frozen 24-operation contract).
"""

from __future__ import annotations

from app.contracts.core import create_contract_app
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


def _operations_by_id(document: dict[str, object]) -> dict[str, dict[str, object]]:
    operations: dict[str, dict[str, object]] = {}
    paths = document["paths"]
    assert isinstance(paths, dict)
    for item in paths.values():
        assert isinstance(item, dict)
        for method, operation in item.items():
            if method not in _HTTP_METHODS:
                continue
            assert isinstance(operation, dict)
            operations[operation["operationId"]] = operation
    return operations


def _required_headers(operation: dict[str, object]) -> set[str]:
    parameters = operation.get("parameters", [])
    assert isinstance(parameters, list)
    return {
        parameter["name"]
        for parameter in parameters
        if isinstance(parameter, dict)
        and parameter.get("in") == "header"
        and parameter.get("required") is True
    }


def test_runtime_implements_every_required_contract_operation() -> None:
    contract = _operations(create_contract_app().openapi())
    runtime = _operations(create_app().openapi())

# The required set is the full frozen contract surface.
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
    contract = _operations(create_contract_app().openapi())
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


def test_required_operations_declare_the_same_required_headers() -> None:
    contract = _operations_by_id(create_contract_app().openapi())
    runtime = _operations_by_id(create_app().openapi())

    mismatched = {
        operation_id: {
            "contract": sorted(_required_headers(operation)),
            "runtime": sorted(_required_headers(runtime[operation_id])),
        }
        for operation_id, operation in contract.items()
        if _required_headers(operation) != _required_headers(runtime[operation_id])
    }

    assert not mismatched, f"required header mismatch: {mismatched}"


def test_required_operations_use_the_same_success_response_schema() -> None:
    contract = _operations_by_id(create_contract_app().openapi())
    runtime = _operations_by_id(create_app().openapi())

    mismatched: dict[str, object] = {}
    for operation_id, operation in contract.items():
        contract_responses = operation["responses"]
        runtime_responses = runtime[operation_id]["responses"]
        assert isinstance(contract_responses, dict)
        assert isinstance(runtime_responses, dict)
        contract_success = {
            status: response
            for status, response in contract_responses.items()
            if str(status).startswith("2")
        }
        runtime_success = {
            status: response
            for status, response in runtime_responses.items()
            if str(status).startswith("2")
        }
        if contract_success != runtime_success:
            mismatched[operation_id] = {
                "contract": contract_success,
                "runtime": runtime_success,
            }

    assert not mismatched, f"success response mismatch: {mismatched}"
