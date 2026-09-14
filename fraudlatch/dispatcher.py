"""Standalone transactional outbox dispatcher."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fraudlatch.contracts import EventEnvelope, TransactionReceivedPayload
from fraudlatch.db.models import OutboxEvent
from fraudlatch.db.session import create_session_factory
from fraudlatch.queue import RedisStreamsQueue, create_redis_client
from fraudlatch.queue.ports import QueuePort
from fraudlatch.queue.retry import classify_processing_error


class DispatcherMetrics(Protocol):
    """Optional metrics sink for dispatcher state changes."""

    def pending(self, count: int) -> None:
        """Record the number of rows selected for publication."""

    def published(self) -> None:
        """Record a successful publication."""

    def failed(self, error_code: str) -> None:
        """Record a terminal publication failure."""


class NullDispatcherMetrics:
    """No-op metrics sink for local development."""

    def pending(self, count: int) -> None:
        pass

    def published(self) -> None:
        pass

    def failed(self, error_code: str) -> None:
        pass


class OutboxDispatcher:
    """Poll pending outbox rows and publish them through QueuePort."""

    batch_size = 100

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | Callable[[], Any],
        queue: QueuePort,
        *,
        metrics: DispatcherMetrics | None = None,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self.session_factory = session_factory
        self.queue = queue
        self.metrics = metrics or NullDispatcherMetrics()
        self.poll_interval_seconds = poll_interval_seconds

    async def dispatch_once(self) -> int:
        """Publish one locked batch and return the number of selected rows."""

        now = datetime.now(UTC)
        async with self.session_factory() as session:
            result = await session.execute(
                select(OutboxEvent)
                .where(
                    OutboxEvent.status == "pending",
                    or_(OutboxEvent.next_attempt_at.is_(None), OutboxEvent.next_attempt_at <= now),
                )
                .order_by(OutboxEvent.created_at)
                .limit(self.batch_size)
                .with_for_update(skip_locked=True)
            )
            events = list(result.scalars().all())
            self.metrics.pending(len(events))
            for event in events:
                await self._dispatch_event(session, event, now)
            await session.commit()
            return len(events)

    async def _dispatch_event(
        self, session: AsyncSession, event: OutboxEvent, now: datetime
    ) -> None:
        event.attempts += 1
        try:
            envelope = EventEnvelope[TransactionReceivedPayload](
                event_id=UUID(event.event_id),
                event_type=event.event_type,
                schema_version=event.schema_version,
                occurred_at=event.occurred_at,
                aggregate_id=event.aggregate_id,
                payload=TransactionReceivedPayload.model_validate(event.payload),
            )
            await self.queue.publish(envelope)
        except Exception as error:
            error_code, transient = classify_processing_error(error)
            event.last_error = f"{error_code}: {error}"[:512]
            if transient:
                event.status = "pending"
                event.next_attempt_at = now + timedelta(
                    seconds=1 if event.attempts == 1 else 5 if event.attempts == 2 else 60
                )
            else:
                event.status = "failed"
                event.next_attempt_at = None
                self.metrics.failed(error_code)
            return

        event.status = "published"
        event.published_at = now
        event.next_attempt_at = None
        event.last_error = None
        self.metrics.published()

    async def run(self, stop_event: asyncio.Event) -> None:
        """Poll until stop_event is set, allowing the current batch to finish."""

        while not stop_event.is_set():
            await self.dispatch_once()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.poll_interval_seconds)
            except TimeoutError:
                pass


async def main() -> None:
    """Run the production-style local dispatcher process."""

    client = create_redis_client()
    queue = RedisStreamsQueue(client)
    await queue.ensure_group()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    try:
        await OutboxDispatcher(create_session_factory(), queue).run(stop_event)
    finally:
        await queue.close()


if __name__ == "__main__":
    asyncio.run(main())
