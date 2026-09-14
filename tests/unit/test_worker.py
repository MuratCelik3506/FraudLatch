import asyncio
from typing import Any
from uuid import uuid4

from fraudlatch.contracts import EventEnvelope, TransactionReceivedPayload
from fraudlatch.queue import MessageHandle, QueueMessage
from fraudlatch.worker import WorkerLoop, WorkerProcessor


class FakeQueue:
    def __init__(self) -> None:
        self.acks: list[str] = []
        self.nacks: list[str] = []

    async def consume(self, **_: Any) -> list[QueueMessage]:
        return []

    async def ack(self, handle: MessageHandle) -> None:
        self.acks.append(handle.message_id)

    async def nack(self, handle: MessageHandle, *, reason: str) -> None:
        self.nacks.append(reason)


class FakeStore:
    def __init__(self, status: str | None = None) -> None:
        self.status = status
        self.actions: list[str] = []

    async def transaction_exists(self, _: str) -> bool:
        return True

    async def assessment_status(self, _: str) -> str | None:
        return self.status

    async def mark_processing(self, _: str, __: int) -> None:
        self.actions.append("processing")

    async def commit(self) -> None:
        self.actions.append("commit")

    async def rollback(self) -> None:
        self.actions.append("rollback")


class FakeRetry:
    def __init__(self) -> None:
        self.errors: list[BaseException] = []

    async def handle_failure(self, event: Any, *, attempt: int, error: BaseException) -> None:
        self.errors.append(error)


def make_message() -> QueueMessage:
    event = EventEnvelope[TransactionReceivedPayload](
        event_id=uuid4(),
        event_type="transaction.received",
        schema_version=1,
        occurred_at="2026-01-01T00:00:00Z",
        aggregate_id="txn-1",
        payload=TransactionReceivedPayload(
            transaction_id="txn-1",
            customer_id="c",
            merchant_id="m",
            category="cat",
            amount="10.00",
            source_step=1,
            event_time="2026-01-01T00:00:00Z",
        ),
    )
    return QueueMessage(
        handle=MessageHandle(queue="q", message_id="1-0"),
        event=event,
        raw_payload=event.model_dump_json(),
        attempts=2,
    )


def test_worker_commits_before_ack_and_is_idempotent() -> None:
    async def exercise() -> None:
        queue, store, retry = FakeQueue(), FakeStore(), FakeRetry()
        calls: list[str] = []

        async def handler(_: Any) -> None:
            calls.append("risk")

        processor = WorkerProcessor(queue, store, handler, retry)  # type: ignore[arg-type]
        assert await processor.process(make_message())
        assert store.actions == ["processing", "commit", "commit"]
        assert calls == ["risk"]
        assert queue.acks == ["1-0"]

        store.status = "completed"
        assert await processor.process(make_message())
        assert calls == ["risk"]
        assert queue.acks == ["1-0", "1-0"]

    asyncio.run(exercise())


def test_worker_does_not_ack_when_risk_calculation_fails() -> None:
    async def exercise() -> None:
        queue, store, retry = FakeQueue(), FakeStore(), FakeRetry()

        async def handler(_: Any) -> None:
            raise TimeoutError("risk service")

        processor = WorkerProcessor(queue, store, handler, retry)  # type: ignore[arg-type]
        assert not await processor.process(make_message())
        assert queue.acks == []
        assert len(queue.nacks) == 1
        assert len(retry.errors) == 1

    asyncio.run(exercise())


def test_worker_loop_stops_without_intake_after_shutdown() -> None:
    async def exercise() -> None:
        queue = FakeQueue()
        stop = asyncio.Event()
        stop.set()
        loop = WorkerLoop(queue, object(), consumer="worker-1")  # type: ignore[arg-type]
        await loop.run(stop)
        assert queue.acks == []

    asyncio.run(exercise())
