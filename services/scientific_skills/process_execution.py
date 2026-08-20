"""Hard-terminating process boundary for registered scientific skills."""

from __future__ import annotations

import asyncio
from multiprocessing import get_context
from multiprocessing.connection import Connection
from time import monotonic
from typing import Literal

from .registry import ScientificSkillRegistry
from .types import ScientificSkillRequest, ScientificSkillResult


class ScientificSkillProcessError(RuntimeError):
    """A child skill process failed outside a declared validation boundary."""


class ScientificSkillProcessExecutor:
    """Run one registered skill in a disposable, hard-terminating process."""

    def __init__(self, registry: ScientificSkillRegistry) -> None:
        self._registry = registry
        self._context = get_context("spawn")

    async def execute(self, request: ScientificSkillRequest) -> ScientificSkillResult:
        receiver, sender = self._context.Pipe(duplex=False)
        process = self._context.Process(
            target=_execute_skill,
            args=(sender, self._registry, request.model_dump(mode="json")),
            name=f"scientific-skill-{request.skill_id.value}",
            daemon=True,
        )
        deadline = monotonic() + request.budget.timeout_seconds
        process.start()
        sender.close()
        try:
            while True:
                if receiver.poll():
                    message = receiver.recv()
                    return _decode_message(message)
                if not process.is_alive():
                    raise ScientificSkillProcessError(
                        "scientific skill process exited without a result"
                    )
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        "scientific skill exceeded "
                        f"{request.budget.timeout_seconds}s budget"
                    )
                await asyncio.sleep(min(0.02, remaining))
        finally:
            receiver.close()
            await asyncio.to_thread(_reap_process, process)


def _execute_skill(
    sender: Connection,
    registry: ScientificSkillRegistry,
    raw_request: dict[str, object],
) -> None:
    try:
        request = ScientificSkillRequest.model_validate(raw_request)
        result = registry.execute(request)
        sender.send(("completed", result.model_dump(mode="json")))
    except (TypeError, ValueError, TimeoutError) as exc:
        sender.send(("declared_error", type(exc).__name__, str(exc)))
    except BaseException as exc:  # noqa: BLE001 - child must report and terminate
        sender.send(("process_error", type(exc).__name__, str(exc)))
    finally:
        sender.close()


def _decode_message(
    message: tuple[Literal["completed"], dict[str, object]]
    | tuple[Literal["declared_error", "process_error"], str, str],
) -> ScientificSkillResult:
    status = message[0]
    if status == "completed":
        return ScientificSkillResult.model_validate(message[1])
    exception_name, detail = message[1], message[2]
    if status == "declared_error":
        exception_type = {
            "TypeError": TypeError,
            "ValueError": ValueError,
            "TimeoutError": TimeoutError,
        }.get(exception_name, ValueError)
        raise exception_type(detail)
    raise ScientificSkillProcessError(
        f"scientific skill process failed with {exception_name}: {detail}"
    )


def _reap_process(process: object) -> None:
    is_alive = getattr(process, "is_alive")
    join = getattr(process, "join")
    if is_alive():
        getattr(process, "terminate")()
    join(1.0)
    if is_alive():
        getattr(process, "kill")()
        join(1.0)
    if is_alive():
        raise ScientificSkillProcessError(
            "scientific skill process could not be terminated"
        )


__all__ = ["ScientificSkillProcessError", "ScientificSkillProcessExecutor"]
