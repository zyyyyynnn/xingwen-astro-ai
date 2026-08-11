"""Shared canonical hashing for versioned declarative contracts."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from pydantic import BaseModel


def compute_canonical_payload_hash(payload: Any) -> str:
    """Hash one JSON-compatible payload with the shared canonical rules."""

    canonical_json = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return f"sha256:{sha256(canonical_json.encode('utf-8')).hexdigest()}"


def compute_canonical_model_hash(model: BaseModel) -> str:
    """Hash a validated model using the canonical Case and Field Manifest JSON rules.

    Object keys are sorted, array order is preserved, null values are omitted,
    UTF-8 is used without ASCII escaping, and the top-level ``content_hash``
    field is excluded by the caller's payload model.
    """

    payload = model.model_dump(mode="json", exclude_none=True)
    return compute_canonical_payload_hash(payload)
