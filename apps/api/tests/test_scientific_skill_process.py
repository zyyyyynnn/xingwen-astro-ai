from __future__ import annotations

from pathlib import Path
from time import sleep
from uuid import uuid4

import pytest

from app.schemas.core import ScientificSkillId
from services.scientific_skills import (
    ScientificSkillBudget,
    ScientificSkillDefinition,
    ScientificSkillProcessExecutor,
    ScientificSkillRegistry,
    ScientificSkillRequest,
)


def _slow_process_handler(request: ScientificSkillRequest) -> dict[str, object]:
    marker = Path(str(request.parameters["marker_path"]))
    marker.write_text("started", encoding="utf-8")
    sleep(2)
    marker.write_text("completed", encoding="utf-8")
    return {"status": "completed"}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_process_executor_hard_terminates_a_timed_out_skill(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "child-status.txt"
    registry = ScientificSkillRegistry(
        (
            ScientificSkillDefinition(
                skill_id=ScientificSkillId.data_profile,
                revision="test",
                handler=_slow_process_handler,
            ),
        )
    )
    request = ScientificSkillRequest(
        request_id="request.timeout",
        project_id=str(uuid4()),
        run_id=str(uuid4()),
        skill_id=ScientificSkillId.data_profile,
        parameters={"marker_path": str(marker)},
        source_references=(),
        budget=ScientificSkillBudget(timeout_seconds=1),
    )

    with pytest.raises(TimeoutError, match="exceeded 1s"):
        await ScientificSkillProcessExecutor(registry).execute(request)

    sleep(1.5)
    assert marker.read_text(encoding="utf-8") == "started"
