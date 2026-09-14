import asyncio
from datetime import UTC, datetime
from typing import Any

from fraudlatch.db.models import OutboxEvent
from fraudlatch.dispatcher import OutboxDispatcher


class FakeResult:
    def __init__(self, events: list[OutboxEvent]) -> None:
        self.events = events

    def scalars(self) -> "FakeResult":
        return self

    def all(self) -> list[OutboxEvent]:
        return self.events


class FakeSession:
    def __init__(self, events: list[OutboxEvent]) -> None:
        self.events = events
        self.commits = 0

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def execute(self, _: Any) -> FakeResult:
        return FakeResult(self.events)

    async def commit(self) -> None:
        self.commits += 1


class FakeQueue:
    def __init__(self, *, error: BaseException | None = None) -> None:
        self.error = error
        self.published: list[Any] = []

    async def publish(self, event: Any) -> None:
        if self.error:
            raise self.error
        self.published.append(event)


def outbox_event(**changes: Any) -> OutboxEvent:
    values: dict[str, Any] = {
        "event_id": "12345678-1234-5678-1234-567812345678",
        "event_type": "transaction.received",
        "schema_version": 1,
        "occurred_at": datetime(2026, 1, 1, tzinfo=UTC),
        "aggregate_id": "txn-1",
        "payload": {
            "transaction_id": "txn-1",
            "customer_id": "customer-1",
            "merchant_id": "merchant-1",
            "category": "es_transportation",
            "amount": "12.34",
            "source_step": 1,
            "source": "api",
            "event_time": "2026-01-01T00:00:00Z",
        },
        "status": "pending",
        "attempts": 0,
    }
    values.update(changes)
    return OutboxEvent(**values)


def test_dispatcher_publishes_exact_event_and_marks_row() -> None:
    async def exercise() -> None:
        event = outbox_event()
        session = FakeSession([event])
        queue = FakeQueue()
        dispatcher = OutboxDispatcher(lambda: session, queue)  # type: ignore[arg-type]

        selected = await dispatcher.dispatch_once()

        assert selected == 1
        assert event.status == "published"
        assert event.published_at is not None
        assert event.attempts == 1
        assert queue.published[0].event_id.hex == event.event_id.replace("-", "")
        assert session.commits == 1

    asyncio.run(exercise())


def test_transient_queue_failure_retains_pending_row_for_retry() -> None:
    async def exercise() -> None:
        event = outbox_event()
        session = FakeSession([event])
        dispatcher = OutboxDispatcher(
            lambda: session,
            FakeQueue(error=ConnectionError("Redis down")),  # type: ignore[arg-type]
        )

        await dispatcher.dispatch_once()

        assert event.status == "pending"
        assert event.attempts == 1
        assert event.next_attempt_at is not None
        assert event.last_error.startswith("dependency_unavailable:")

    asyncio.run(exercise())


def test_malformed_event_is_failed_and_remains_visible() -> None:
    async def exercise() -> None:
        event = outbox_event(payload={"transaction_id": "missing-fields"})
        session = FakeSession([event])
        dispatcher = OutboxDispatcher(lambda: session, FakeQueue())  # type: ignore[arg-type]

        await dispatcher.dispatch_once()

        assert event.status == "failed"
        assert event.next_attempt_at is None
        assert event.last_error.startswith("invalid_event:")

    asyncio.run(exercise())
