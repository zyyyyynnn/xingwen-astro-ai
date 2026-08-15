import asyncio
from types import SimpleNamespace

from app.services.content_storage import ContentStorageError
from app.services.model_execution import ModelExecutionError
from app.services.research import _queue_capacity_problem
from app.workflow.research_run_worker import ResearchRunWorker
from app.workflow.document_pipeline_runtime import DocumentPipelineInputError
from app.workflow.store import RunQueueCapacityError


def test_model_failure_preserves_safe_message_and_retry_policy() -> None:
    retryable = ResearchRunWorker._classify_failure(
        ModelExecutionError(
            "MODEL_PROVIDER_TIMEOUT",
            "研究助手响应超时，请稍后重试。",
            provider_request_id="provider-1",
        )
    )
    invalid = ResearchRunWorker._classify_failure(
        ModelExecutionError(
            "MODEL_RESPONSE_INVALID",
            "研究助手返回了无法验证的结果。",
        )
    )

    assert retryable.retryable is True
    assert retryable.upstream_request_id == "provider-1"
    assert invalid.retryable is False


def test_internal_failure_does_not_leak_private_details() -> None:
    internal = "C:\\private\\secret.txt: provider payload"

    decision = ResearchRunWorker._classify_failure(ValueError(internal))

    assert decision.error_code == "RUN_EXECUTION_FAILED"
    assert internal not in decision.public_message


def test_content_storage_failure_is_retryable() -> None:
    decision = ResearchRunWorker._classify_failure(
        ContentStorageError("private filesystem detail")
    )

    assert decision.error_code == "CONTENT_STORAGE_UNAVAILABLE"
    assert decision.retryable is True


def test_queue_capacity_maps_to_stable_retryable_http_problem() -> None:
    problem = _queue_capacity_problem(
        RunQueueCapacityError(scope="project", retry_after_seconds=7)
    )

    assert problem.status == 429
    assert problem.code == "RUN_QUEUE_CAPACITY_EXCEEDED"
    assert problem.headers == {"Retry-After": "7"}
    assert "this project" in problem.detail


def test_missing_document_is_the_only_explicit_input_checkpoint_classification() -> (
    None
):
    decision = ResearchRunWorker._classify_failure(
        DocumentPipelineInputError("private input lookup detail")
    )

    assert decision.error_code == "DOCUMENT_INPUT_REQUIRED"
    assert decision.retryable is False
    assert decision.checkpoint is not None
    assert decision.checkpoint.required_input_types == ("pdf", "text")
    assert "private input lookup detail" not in decision.public_message


def test_cleaning_data_prepares_the_complete_publication_set() -> None:
    decision = object()
    publications = (object(), object(), object())
    calls: dict[str, object] = {}

    async def select_step(**kwargs: object) -> object:
        calls["agent_kwargs"] = kwargs
        return decision

    class _Data:
        def prepare_publications(self, **kwargs: object) -> tuple[object, ...]:
            calls["data_kwargs"] = kwargs
            return publications

    worker = object.__new__(ResearchRunWorker)
    worker._select_step = select_step
    worker._data = _Data()
    contract = SimpleNamespace(model_dump=lambda **kwargs: {"goal": "data"})
    context = SimpleNamespace(contract=contract)
    step = SimpleNamespace(key="cleaning_data", task_id=None, skill_id=None)
    attempt = object()
    lease = object()

    prepared = asyncio.run(worker._prepare_step(context, step, attempt, lease))

    assert prepared.decision is decision
    assert prepared.scientific_output is None
    assert prepared.publications is publications
    assert calls["data_kwargs"] == {
        "contract": contract,
        "step_key": "cleaning_data",
        "attempt": attempt,
        "lease": lease,
    }


def test_worker_cancels_an_active_operation_after_run_cancellation() -> None:
    finished = asyncio.Event()

    class _Store:
        def load_snapshot(self, _run_id: object) -> object:
            return SimpleNamespace(status="cancelled")

    async def operation() -> None:
        try:
            await asyncio.Future()
        finally:
            finished.set()

    async def exercise() -> None:
        worker = object.__new__(ResearchRunWorker)
        worker._store = _Store()
        completed = await worker._execute_until_cancelled(object(), operation())
        assert completed is False
        assert finished.is_set()

    asyncio.run(exercise())


def test_worker_stop_requests_drain_and_allows_active_work_to_finish() -> None:
    async def exercise() -> None:
        calls: list[str] = []
        release = asyncio.Event()
        finished = asyncio.Event()

        class _Registry:
            def request_drain(self, worker_id: str) -> None:
                calls.append(worker_id)

        async def block() -> None:
            await release.wait()
            finished.set()

        worker = object.__new__(ResearchRunWorker)
        worker._registry = _Registry()
        worker.worker_id = "worker-test"
        worker._stop = asyncio.Event()
        worker._task = asyncio.create_task(block())
        stopping = asyncio.create_task(worker.stop())
        await asyncio.sleep(0)

        assert calls == ["worker-test"]
        assert worker._task is not None
        assert worker._task.cancelled() is False

        release.set()
        await stopping
        assert worker._task is None
        assert finished.is_set()

    asyncio.run(exercise())


def test_worker_lease_owner_matches_the_persisted_worker_identity() -> None:
    owners: list[str] = []

    class _Store:
        def __init__(self) -> None:
            self.snapshot_count = 0

        def load_snapshot(self, _run_id: object) -> object:
            self.snapshot_count += 1
            status = "queued" if self.snapshot_count == 1 else "completed"
            return SimpleNamespace(status=status, revision=1)

        def acquire_lease(self, _run_id: object, **kwargs: object) -> object:
            owners.append(str(kwargs["owner"]))
            return object()

    async def exercise() -> None:
        worker = object.__new__(ResearchRunWorker)
        worker._registered = False
        worker.worker_id = "worker-health-identity"
        worker._store = _Store()
        worker._load_context = lambda _run_id: object()

        await worker.execute_run(object())

    asyncio.run(exercise())

    assert owners == ["worker-health-identity"]


def test_searching_papers_uses_contract_search_runtime_without_document_gate() -> None:
    decision = object()
    publication = object()
    calls: dict[str, object] = {}

    async def select_step(**_kwargs: object) -> object:
        return decision

    class _PaperSearch:
        def prepare_publication(self, **kwargs: object) -> object:
            calls["kwargs"] = kwargs
            return publication

    worker = object.__new__(ResearchRunWorker)
    worker._select_step = select_step
    worker._paper_search = _PaperSearch()
    context = SimpleNamespace(
        run_id="run-1",
        project_id="project-1",
        contract=SimpleNamespace(model_dump=lambda **kwargs: {"goal": "papers"}),
    )
    step = SimpleNamespace(key="searching_papers", task_id=None, skill_id=None)
    attempt = object()
    lease = object()

    prepared = asyncio.run(worker._prepare_step(context, step, attempt, lease))

    assert prepared.decision is decision
    assert prepared.publications == (publication,)
    assert calls["kwargs"] == {
        "project_id": "project-1",
        "contract": context.contract,
        "attempt": attempt,
        "lease": lease,
    }
