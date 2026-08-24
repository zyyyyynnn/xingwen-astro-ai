from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

from app.schemas._hashing import compute_canonical_payload_hash
from app.services.model_execution import ModelExecutionRequest, ModelExecutionResponse
from app.workflow.publisher import ProducerExecutionSnapshot
from app.workflow.step_publication import (
    RunStepContext,
    StepModelCaller,
    StepPublicationFactory,
    TrackedStepModelExecutionPort,
)
from app.workflow.store import AttemptHandle, LeaseGrant
from packages.prompts.registry import PromptRegistry


def test_completed_agent_model_execution_replays_without_provider_call() -> None:
    run_id = uuid4()
    step_id = uuid4()
    attempt_id = uuid4()
    execution_id = uuid4()
    now = datetime.now(UTC)
    snapshot = ProducerExecutionSnapshot(
        id=execution_id,
        run_id=run_id,
        run_step_id=step_id,
        step_attempt_id=attempt_id,
        step_key="planning",
        idempotency_key="agent-call",
        lease_generation=1,
        producer_type="model",
        producer_name="research_step_agent",
        producer_version="qwen-test",
        model_provider="qwen",
        requested_model="qwen-test",
        provider_returned_model="qwen-test-202608",
        provider_request_id="provider-request-1",
        explicit_revision=None,
        prompt_name="research_step_agent",
        prompt_version="1.0.0",
        prompt_hash="sha256:" + "a" * 64,
        parameters={"temperature": 0.6},
        parameters_hash="sha256:" + "b" * 64,
        input_hash="sha256:" + "c" * 64,
        output_hash="sha256:" + "d" * 64,
        status="completed",
        started_at=now,
        finished_at=now,
        token_usage={"total_tokens": 24},
        latency_ms=120,
        error_code=None,
        model_response={
            "payload": {},
            "tool_calls": [
                {
                    "id": "tool-call-1",
                    "name": "plan_research_path",
                    "arguments": {
                        "public_analysis": "已核对当前研究步骤的输入与完成条件。"
                    },
                }
            ],
        },
        replayed=True,
    )

    class Provider:
        def execute(self, _request: ModelExecutionRequest):
            raise AssertionError("a completed provider response must be replayed")

    class Publications:
        def start_producer(self, *_args: object, **_kwargs: object):
            return snapshot

        def finish_producer(self, *_args: object, **_kwargs: object):
            raise AssertionError("start_agent_call must not finish the execution")

    port = TrackedStepModelExecutionPort(
        base=Provider(),
        publications=cast(StepPublicationFactory, Publications()),
        context=cast(RunStepContext, object()),
        step_key="planning",
        attempt=AttemptHandle(
            run_id=run_id,
            run_step_id=step_id,
            attempt_id=attempt_id,
            attempt_number=1,
            run_status="planning",
            run_revision=2,
            event_sequence=2,
        ),
        lease=LeaseGrant(
            run_id=run_id,
            token=uuid4(),
            generation=2,
            revision=2,
            expires_at=now + timedelta(minutes=5),
            active_attempt_ids=(attempt_id,),
        ),
    )
    response, returned_execution_id = port.start_agent_call(
        ModelExecutionRequest(
            provider="qwen",
            requested_model="qwen-test",
            explicit_revision=None,
            prompt_name="research_step_agent",
            prompt_version="1.0.0",
            prompt_hash="sha256:" + "a" * 64,
            prompt="Select the only governed tool.",
            input_payload={"step_key": "planning"},
            parameters={"temperature": 0.6},
            response_mode="tool",
        ),
        authorized_tool_name="plan_research_path",
        authorized_skill_id="planning",
        registry_revision="research_step_tools.initial",
    )

    assert returned_execution_id == execution_id
    assert response.provider_request_id == "provider-request-1"
    assert response.tool_calls[0].name == "plan_research_path"
    assert response.tool_calls[0].arguments == {
        "public_analysis": "已核对当前研究步骤的输入与完成条件。"
    }


def test_resumable_child_model_call_reuses_an_earlier_attempt() -> None:
    run_id = uuid4()
    step_id = uuid4()
    earlier_attempt_id = uuid4()
    current_attempt_id = uuid4()
    execution_id = uuid4()
    now = datetime.now(UTC)
    request = ModelExecutionRequest(
        provider="qwen",
        requested_model="qwen-test",
        explicit_revision=None,
        prompt_name="paper_summary",
        prompt_version="1.0.0",
        prompt_hash="sha256:" + "a" * 64,
        prompt="Summarize one deterministic chunk.",
        input_payload={"chunk_id": "chunk.0001"},
        parameters={"temperature": 0},
    )
    response_payload = {"background": [], "evidence_ids": []}
    snapshot = ProducerExecutionSnapshot(
        id=execution_id,
        run_id=run_id,
        run_step_id=step_id,
        step_attempt_id=earlier_attempt_id,
        step_key="summarizing_papers",
        idempotency_key="earlier-chunk-call",
        lease_generation=1,
        producer_type="model",
        producer_name="qwen-chat-completions",
        producer_version="qwen-test",
        model_provider="qwen",
        requested_model="qwen-test",
        provider_returned_model=None,
        provider_request_id="provider-request-chunk-1",
        explicit_revision=None,
        prompt_name="paper_summary",
        prompt_version="1.0.0",
        prompt_hash="sha256:" + "a" * 64,
        parameters={"temperature": 0},
        parameters_hash=request.parameters_hash,
        input_hash=request.input_hash,
        output_hash=compute_canonical_payload_hash(response_payload),
        status="completed",
        started_at=now,
        finished_at=now,
        token_usage={"total_tokens": 8},
        latency_ms=40,
        error_code=None,
        model_response={"payload": response_payload, "tool_calls": []},
        replayed=True,
    )

    class Provider:
        def execute(self, _request: ModelExecutionRequest) -> ModelExecutionResponse:
            raise AssertionError("a completed chunk must not call the provider again")

    class Publications:
        def find_completed_model(self, *_args: object, **_kwargs: object):
            return snapshot

        def start_producer(self, *_args: object, **_kwargs: object):
            raise AssertionError("a replayed chunk must not start another execution")

        def finish_producer(self, execution: object, **_kwargs: object):
            assert execution == execution_id
            return snapshot

    port = TrackedStepModelExecutionPort(
        base=Provider(),
        publications=cast(StepPublicationFactory, Publications()),
        context=cast(RunStepContext, object()),
        step_key="summarizing_papers",
        attempt=AttemptHandle(
            run_id=run_id,
            run_step_id=step_id,
            attempt_id=current_attempt_id,
            attempt_number=2,
            run_status="summarizing_papers",
            run_revision=5,
            event_sequence=5,
        ),
        lease=LeaseGrant(
            run_id=run_id,
            token=uuid4(),
            generation=2,
            revision=5,
            expires_at=now + timedelta(minutes=5),
            active_attempt_ids=(current_attempt_id,),
        ),
    )

    replayed = port.execute_resumable(request)

    assert replayed.payload == response_payload
    assert replayed.provider_request_id == "provider-request-chunk-1"


def test_each_new_step_model_call_resolves_current_runtime_and_provenance() -> None:
    run_id = uuid4()
    step_id = uuid4()
    attempt_id = uuid4()
    now = datetime.now(UTC)
    provider_requests: list[tuple[str, str, str]] = []
    producer_requests: list[dict[str, object]] = []

    class Provider:
        def __init__(self, name: str) -> None:
            self._name = name

        def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
            provider_requests.append(
                (self._name, request.provider, request.requested_model)
            )
            return ModelExecutionResponse(
                payload={"provider": self._name},
                output_hash=compute_canonical_payload_hash({"provider": self._name}),
                token_usage=None,
                latency_ms=1,
                provider_request_id=f"request-{self._name}",
            )

    class Publications:
        def start_producer(self, *_args: object, **kwargs: object):  # noqa: ANN201
            producer_requests.append(kwargs)
            return SimpleNamespace(id=uuid4(), replayed=False)

        def finish_producer(self, *_args: object, **_kwargs: object) -> None:
            return None

    runtimes = iter(
        (
            SimpleNamespace(
                port=Provider("first"),
                provider="qwen",
                requested_model="qwen-first",
                explicit_revision=None,
            ),
            SimpleNamespace(
                port=Provider("second"),
                provider="openai_compatible",
                requested_model="qwen-second",
                explicit_revision="qwen-second-202608",
            ),
        )
    )
    port = TrackedStepModelExecutionPort(
        base=Provider("stale"),
        publications=cast(StepPublicationFactory, Publications()),
        context=cast(RunStepContext, object()),
        step_key="reasoning_literature",
        attempt=AttemptHandle(
            run_id=run_id,
            run_step_id=step_id,
            attempt_id=attempt_id,
            attempt_number=1,
            run_status="reasoning_literature",
            run_revision=2,
            event_sequence=2,
        ),
        lease=LeaseGrant(
            run_id=run_id,
            token=uuid4(),
            generation=1,
            revision=2,
            expires_at=now + timedelta(minutes=5),
            active_attempt_ids=(attempt_id,),
        ),
        runtime_resolver=lambda: next(runtimes),
    )
    request = ModelExecutionRequest(
        provider="qwen",
        requested_model="stale-model",
        explicit_revision=None,
        prompt_name="literature_claim",
        prompt_version="1.0.0",
        prompt_hash="sha256:" + "a" * 64,
        prompt="Extract claims.",
        input_payload={"paper": "one"},
        parameters={"temperature": 0},
    )

    port.execute(request)
    port.execute(request)

    assert provider_requests == [
        ("first", "qwen", "qwen-first"),
        ("second", "openai_compatible", "qwen-second"),
    ]
    assert [item["model_provider"] for item in producer_requests] == [
        "qwen",
        "openai_compatible",
    ]
    assert [item["requested_model"] for item in producer_requests] == [
        "qwen-first",
        "qwen-second",
    ]
    assert producer_requests[1]["explicit_revision"] == "qwen-second-202608"


def test_chunked_summary_pins_one_runtime_until_the_parent_call_finishes() -> None:
    run_id = uuid4()
    step_id = uuid4()
    attempt_id = uuid4()
    now = datetime.now(UTC)
    provider_models: list[str] = []
    producer_models: list[str] = []

    class Provider:
        def __init__(self, model: str) -> None:
            self._model = model

        def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
            provider_models.append(request.requested_model)
            assert request.requested_model == self._model
            return ModelExecutionResponse(
                payload={"model": self._model},
                output_hash=compute_canonical_payload_hash({"model": self._model}),
                token_usage=None,
                latency_ms=1,
                provider_request_id=f"request-{self._model}",
            )

    class Publications:
        def find_completed_model(self, *_args: object, **_kwargs: object):  # noqa: ANN201
            return None

        def start_producer(self, *_args: object, **kwargs: object):  # noqa: ANN201
            producer_models.append(cast(str, kwargs["requested_model"]))
            return SimpleNamespace(id=uuid4(), replayed=False)

        def finish_producer(self, *_args: object, **_kwargs: object) -> None:
            return None

    runtimes = iter(
        (
            SimpleNamespace(
                port=Provider("qwen-pinned"),
                provider="qwen",
                requested_model="qwen-pinned",
                explicit_revision=None,
            ),
            SimpleNamespace(
                port=Provider("qwen-next"),
                provider="qwen",
                requested_model="qwen-next",
                explicit_revision=None,
            ),
        )
    )
    tracked = TrackedStepModelExecutionPort(
        base=Provider("stale-model"),
        publications=cast(StepPublicationFactory, Publications()),
        context=cast(RunStepContext, object()),
        step_key="summarizing_papers",
        attempt=AttemptHandle(
            run_id=run_id,
            run_step_id=step_id,
            attempt_id=attempt_id,
            attempt_number=1,
            run_status="summarizing_papers",
            run_revision=2,
            event_sequence=2,
        ),
        lease=LeaseGrant(
            run_id=run_id,
            token=uuid4(),
            generation=1,
            revision=2,
            expires_at=now + timedelta(minutes=5),
            active_attempt_ids=(attempt_id,),
        ),
        runtime_resolver=lambda: next(runtimes),
    )
    caller = StepModelCaller(
        model_port=tracked,
        provider="qwen",
        requested_model="stale-model",
        explicit_revision=None,
        prompts=cast(PromptRegistry, object()),
    )
    chunks = caller.pin_resumable_port()
    assert caller.requested_model == "qwen-pinned"

    for chunk_id in ("chunk.0001", "chunk.0002"):
        chunks.execute(
            ModelExecutionRequest(
                provider="qwen",
                requested_model="stale-model",
                explicit_revision=None,
                prompt_name="paper_summary",
                prompt_version="1.0.0",
                prompt_hash="sha256:" + "a" * 64,
                prompt="Summarize one chunk.",
                input_payload={"chunk_id": chunk_id},
                parameters={"temperature": 0},
            )
        )

    tracked.execute(
        ModelExecutionRequest(
            provider="qwen",
            requested_model="stale-model",
            explicit_revision=None,
            prompt_name="literature_claim",
            prompt_version="1.0.0",
            prompt_hash="sha256:" + "b" * 64,
            prompt="Start the next independent call.",
            input_payload={"paper": "one"},
            parameters={"temperature": 0},
        )
    )

    assert provider_models == ["qwen-pinned", "qwen-pinned", "qwen-next"]
    assert producer_models == ["qwen-pinned", "qwen-pinned", "qwen-next"]
