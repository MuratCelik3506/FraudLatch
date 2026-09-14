"""Restart-safe worker lifecycle for transaction events."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

from fraudlatch.contracts import EventEnvelope
from fraudlatch.queue import QueueMessage, QueuePort, RedisRetryHandler
from fraudlatch.queue.retry import PermanentProcessingError

logger = logging.getLogger(__name__)


class WorkerStore(Protocol):
    """Persistence boundary required by the worker."""

    async def transaction_exists(self, transaction_id: str) -> bool: ...

    async def assessment_status(self, transaction_id: str) -> str | None: ...

    async def mark_processing(self, transaction_id: str, attempt: int) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


RiskHandler = Callable[[EventEnvelope[Any]], Awaitable[None]]


class WorkerProcessor:
    """Process one message and acknowledge it only after a durable commit."""

    def __init__(
        self,
        queue: QueuePort,
        store: WorkerStore,
        risk_handler: RiskHandler,
        retry_handler: RedisRetryHandler,
    ) -> None:
        self.queue = queue
        self.store = store
        self.risk_handler = risk_handler
        self.retry_handler = retry_handler

    async def process(self, message: QueueMessage) -> bool:
        """Return true when the message was acknowledged successfully."""

        try:
            event = message.event
            if event.event_type != "transaction.received":
                raise PermanentProcessingError("unsupported worker event type")
            transaction_id = event.aggregate_id
            if not await self.store.transaction_exists(transaction_id):
                raise PermanentProcessingError("transaction not found")
            if await self.store.assessment_status(transaction_id) == "completed":
                await self.queue.ack(message.handle)
                return True

            # This marker is committed separately so a crash during calculation is
            # visible after restart and can be reclaimed by the next consumer.
            await self.store.mark_processing(transaction_id, message.attempts)
            await self.store.commit()
            await self.risk_handler(event)
            await self.store.commit()
        except Exception as error:
            await self.store.rollback()
            await self.retry_handler.handle_failure(
                message.event, attempt=message.attempts, error=error
            )
            await self.queue.nack(message.handle, reason=str(error) or "processing failure")
            return False

        # Ack is deliberately the final side effect: DB is authoritative.
        await self.queue.ack(message.handle)
        return True


class WorkerLoop:
    """Consume until shutdown, finishing the message already in flight."""

    def __init__(self, queue: QueuePort, processor: WorkerProcessor, *, consumer: str) -> None:
        if not consumer:
            raise ValueError("consumer must not be empty")
        self.queue = queue
        self.processor = processor
        self.consumer = consumer

    async def run(self, stop_event: asyncio.Event) -> None:
        """Stop intake on SIGTERM while allowing the current batch to finish."""

        while not stop_event.is_set():
            messages: Sequence[QueueMessage] = await self.queue.consume(
                consumer=self.consumer, count=1, block_ms=500
            )
            for message in messages:
                await self.processor.process(message)
                if stop_event.is_set():
                    return
