"""Print a read-only content integrity and orphan impact report as JSON."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
import sys

from app.config import settings
from app.db.session import create_engine_from_url, session_factory
from app.services.content_lifecycle import ContentLifecycleService
from app.services.content_storage import LocalContentStorage
from app.services.resource_authority import PersistentResourceAuthority


async def _audit() -> int:
    if settings.DATABASE_URL is None:
        raise RuntimeError("DATABASE_URL is required for an authoritative audit")
    engine = create_engine_from_url(settings.DATABASE_URL.get_secret_value())
    try:
        authority = PersistentResourceAuthority(session_factory(engine))
        report = await ContentLifecycleService(
            storage=LocalContentStorage(settings.RESEARCH_INPUT_UPLOAD_DIR),
            authority=authority,
        ).inspect()
    finally:
        engine.dispose()
    payload = asdict(report)
    payload["integrity_ok"] = report.integrity_ok
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report.integrity_ok else 2


def main() -> int:
    """Run the read-only audit; exit 2 when integrity is not closed."""

    try:
        return asyncio.run(_audit())
    except Exception:  # noqa: BLE001 - operator boundary must not leak internals
        print(
            json.dumps(
                {
                    "code": "CONTENT_STORAGE_AUDIT_FAILED",
                    "detail": "The authoritative content audit could not be completed.",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised by operator invocation
    raise SystemExit(main())
