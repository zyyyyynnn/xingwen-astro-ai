"""Fail-closed ONNX inference for project-owned ModelArtifacts."""

from __future__ import annotations

from base64 import b64decode
from hashlib import sha256
from math import isfinite
from typing import Any

from .parameters import reject_unknown, require_rows
from .types import ScientificSkillRequest


_MODEL_KEYS = frozenset(
    {
        "model_artifact_version_id",
        "model_id",
        "task_kind",
        "feature_fields",
        "target_field",
        "content_base64",
        "content_hash",
        "media_type",
        "input_name",
        "output_names",
        "input_shape",
        "opset_imports",
    }
)
_ALLOWED_ONNX_DOMAINS = frozenset({"ai.onnx", "ai.onnx.ml"})


def run_model_inference(request: ScientificSkillRequest) -> dict[str, object]:
    """Execute a verified ONNX model with bounded numeric rows on CPU only."""

    reject_unknown(
        request.parameters,
        {"model", "rows", "dataset_artifact_version_id"},
    )
    rows = require_rows(request.parameters, max_rows=request.budget.max_input_rows)
    if len(rows) > request.budget.max_output_rows:
        raise ValueError("model inference output exceeds the row budget")
    dataset_version_id = _text(request.parameters, "dataset_artifact_version_id")
    raw_model = request.parameters.get("model")
    if not isinstance(raw_model, dict) or set(raw_model) != _MODEL_KEYS:
        raise ValueError("model inference requires the exact ModelArtifact contract")
    if raw_model.get("media_type") != "application/onnx":
        raise ValueError("model inference accepts only ONNX ModelArtifacts")

    encoded = _text(raw_model, "content_base64")
    try:
        binary = b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError("ModelArtifact ONNX content is not valid base64") from exc
    if not binary or len(binary) > request.budget.max_input_bytes:
        raise ValueError("ModelArtifact ONNX content exceeds the input byte budget")
    content_hash = _text(raw_model, "content_hash")
    actual_hash = "sha256:" + sha256(binary).hexdigest()
    if content_hash != actual_hash:
        raise ValueError("ModelArtifact ONNX content hash is invalid")

    feature_fields = _string_list(raw_model, "feature_fields", max_items=256)
    input_name = _text(raw_model, "input_name")
    output_names = _string_list(raw_model, "output_names", max_items=32)
    input_shape = _input_shape(raw_model, feature_count=len(feature_fields))
    declared_opsets = _opset_imports(raw_model)
    matrix, row_ids = _numeric_matrix(rows, feature_fields)
    outputs = _execute_onnx(
        binary,
        matrix=matrix,
        input_name=input_name,
        output_names=output_names,
        input_shape=input_shape,
        declared_opsets=declared_opsets,
    )
    predictions = _prediction_rows(row_ids, output_names, outputs)
    return {
        "model_artifact_version_id": _text(
            raw_model, "model_artifact_version_id"
        ),
        "model_id": _text(raw_model, "model_id"),
        "dataset_artifact_version_id": dataset_version_id,
        "task_kind": _text(raw_model, "task_kind"),
        "feature_fields": feature_fields,
        "target_field": _text(raw_model, "target_field"),
        "output_names": output_names,
        "prediction_count": len(predictions),
        "predictions": predictions,
        "model_content_hash": content_hash,
    }


def _execute_onnx(
    binary: bytes,
    *,
    matrix: list[list[float]],
    input_name: str,
    output_names: list[str],
    input_shape: list[int | None],
    declared_opsets: dict[str, int],
) -> list[object]:
    import numpy as np
    import onnx
    import onnxruntime as ort

    model = onnx.load_model_from_string(binary)
    onnx.checker.check_model(model)
    if any(
        initializer.data_location == onnx.TensorProto.EXTERNAL
        or initializer.external_data
        for initializer in model.graph.initializer
    ):
        raise ValueError("ONNX external data is not permitted")
    actual_opsets = {
        item.domain or "ai.onnx": int(item.version) for item in model.opset_import
    }
    if actual_opsets != declared_opsets:
        raise ValueError("ModelArtifact ONNX opsets do not match its contract")
    supported = _supported_opsets(onnx)
    if any(
        domain not in _ALLOWED_ONNX_DOMAINS
        or revision > supported.get(domain, 0)
        for domain, revision in actual_opsets.items()
    ):
        raise ValueError("ModelArtifact uses an unsupported ONNX domain or opset")
    if any(
        (node.domain or "ai.onnx") not in _ALLOWED_ONNX_DOMAINS
        for node in model.graph.node
    ):
        raise ValueError("ModelArtifact contains a custom ONNX operator domain")

    options = ort.SessionOptions()
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.enable_cpu_mem_arena = False
    session = ort.InferenceSession(
        binary,
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
    inputs = session.get_inputs()
    if len(inputs) != 1 or inputs[0].name != input_name:
        raise ValueError("ModelArtifact ONNX input does not match its contract")
    if [item.name for item in session.get_outputs()] != output_names:
        raise ValueError("ModelArtifact ONNX outputs do not match its contract")
    runtime_shape = inputs[0].shape
    if len(runtime_shape) != len(input_shape) or (
        isinstance(runtime_shape[-1], int) and runtime_shape[-1] != input_shape[-1]
    ):
        raise ValueError("ModelArtifact ONNX input shape does not match its contract")
    return list(
        session.run(
            output_names,
            {input_name: np.asarray(matrix, dtype=np.float32)},
        )
    )


def _supported_opsets(onnx: Any) -> dict[str, int]:
    supported: dict[str, int] = {"ai.onnx": int(onnx.defs.onnx_opset_version())}
    for schema in onnx.defs.get_all_schemas_with_history():
        domain = schema.domain or "ai.onnx"
        if domain in _ALLOWED_ONNX_DOMAINS:
            supported[domain] = max(supported.get(domain, 0), schema.since_version)
    return supported


def _numeric_matrix(
    rows: tuple[dict[str, Any], ...],
    feature_fields: list[str],
) -> tuple[list[list[float]], list[str]]:
    matrix: list[list[float]] = []
    row_ids: list[str] = []
    for position, row in enumerate(rows, start=1):
        values: list[float] = []
        for field in feature_fields:
            raw = row.get(field)
            if (
                isinstance(raw, bool)
                or not isinstance(raw, int | float)
                or not isfinite(float(raw))
            ):
                raise ValueError(
                    f"model inference row {position} has no finite numeric {field}"
                )
            values.append(float(raw))
        matrix.append(values)
        row_ids.append(str(row.get("row_id", f"row.{position}")))
    return matrix, row_ids


def _prediction_rows(
    row_ids: list[str],
    output_names: list[str],
    outputs: list[object],
) -> list[dict[str, object]]:
    normalized = [_json_value(value) for value in outputs]
    if any(not isinstance(value, list) or len(value) != len(row_ids) for value in normalized):
        raise ValueError("ModelArtifact ONNX output batch shape is invalid")
    return [
        {
            "row_id": row_id,
            "outputs": {
                name: normalized[output_index][row_index]  # type: ignore[index]
                for output_index, name in enumerate(output_names)
            },
        }
        for row_index, row_id in enumerate(row_ids)
    ]


def _json_value(value: object) -> object:
    if hasattr(value, "tolist"):
        return _json_value(value.tolist())  # type: ignore[union-attr]
    if hasattr(value, "item"):
        return _json_value(value.item())  # type: ignore[union-attr]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, bool | int | float | str) or value is None:
        if isinstance(value, float) and not isfinite(value):
            raise ValueError("ModelArtifact ONNX output is not finite")
        return value
    raise ValueError("ModelArtifact ONNX output is not JSON-compatible")


def _input_shape(value: dict[str, Any], *, feature_count: int) -> list[int | None]:
    raw = value.get("input_shape")
    if (
        not isinstance(raw, list)
        or raw != [None, feature_count]
        or any(isinstance(item, bool) for item in raw)
    ):
        raise ValueError("ModelArtifact input shape does not match its feature registry")
    return [None, feature_count]


def _opset_imports(value: dict[str, Any]) -> dict[str, int]:
    raw = value.get("opset_imports")
    if not isinstance(raw, dict) or not raw:
        raise ValueError("ModelArtifact has no ONNX opset registry")
    result: dict[str, int] = {}
    for domain, revision in raw.items():
        if (
            not isinstance(domain, str)
            or not domain
            or isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision < 1
        ):
            raise ValueError("ModelArtifact ONNX opset registry is invalid")
        result[domain] = revision
    return result


def _string_list(
    value: dict[str, Any], key: str, *, max_items: int
) -> list[str]:
    raw = value.get(key)
    if (
        not isinstance(raw, list)
        or not raw
        or len(raw) > max_items
        or any(not isinstance(item, str) or not item.strip() for item in raw)
        or len(set(raw)) != len(raw)
    ):
        raise ValueError(f"ModelArtifact {key} registry is invalid")
    return list(raw)


def _text(value: dict[str, Any], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"model inference requires {key}")
    return raw


__all__ = ["run_model_inference"]
