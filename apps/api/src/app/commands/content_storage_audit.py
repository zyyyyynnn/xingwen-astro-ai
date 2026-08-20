"""Print a read-only content integrity and orphan impact report as JSON.

The command is strictly observational: it reads the current ``DATABASE_URL``
and ``RESEARCH_INPUT_UPLOAD_DIR`` configuration, runs the lifecycle inspection
against the authoritative PostgreSQL reference closure and the local
content-addressed store, and prints a deterministic JSON summary.  No blob is
ever deleted: ``deletion_supported`` stays ``false`` until writers and
maintenance share an atomic publication/collection coordination primitive.

Exit codes:
    0 -- integrity closed, no findings
    1 -- integrity findings present
    2 -- configuration or runtime unavailable
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict

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
    return 0 if report.integrity_ok else 1


def main() -> int:
    """Run the read-only audit; exit 1 on findings, 2 when unavailable."""

    try:
        return asyncio.run(_audit())
    except Exception:  # noqa: BLE001 - operator boundary must not leak internals
        print(
            json.dumps(
                {
                    "code": "CONTENT_STORAGE_AUDIT_UNAVAILABLE",
                    "detail": (
                        "The authoritative content audit could not be completed;"
                        " check DATABASE_URL and RESEARCH_INPUT_UPLOAD_DIR."
                    ),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised by operator invocation
    raise SystemExit(main())
