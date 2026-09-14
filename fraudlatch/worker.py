"""Restart-safe worker lifecycle for transaction events."""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol, cast

from sqlalchemy import select

from fraudlatch.api.risk_repository import persist_risk_result
from fraudlatch.contracts import EventEnvelope, TransactionReceivedPayload
from fraudlatch.db.models import RiskAssessment, Transaction
from fraudlatch.db.session import create_session_factory
from fraudlatch.queue import (
    QueueMessage,
    QueuePort,
    RedisRetryHandler,
    RedisStreamsQueue,
    create_redis_client,
)
from fraudlatch.queue.retry import PermanentProcessingError
from fraudlatch.risk import assess
from fraudlatch.risk.models import RiskDecision, RiskTransaction
from fraudlatch.risk.velocity import VelocityContextProvider

logger = logging.getLogger(__name__)


class WorkerStore(Protocol):
    """Persistence boundary required by the worker."""

    async def transaction_exists(self, transaction_id: str) -> bool: ...

    async def assessment_status(self, transaction_id: str) -> str | None: ...

    async def mark_processing(self, transaction_id: str, attempt: int) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...

    async def persist_decision(
        self, transaction_id: str, event_id: str, attempt: int, decision: RiskDecision
    ) -> None: ...


RiskHandler = Callable[[EventEnvelope[Any]], Awaitable[RiskDecision | None]]


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
            decision = await self.risk_handler(event)
            if decision is not None:
                await self.store.persist_decision(
                    transaction_id=transaction_id,
                    event_id=f"{event.event_id}:{message.attempts}",
                    attempt=message.attempts,
                    decision=decision,
                )
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


class DatabaseWorkerStore:
    """PostgreSQL-backed worker store used by the executable worker."""

    def __init__(self, session: Any) -> None:
        self.session = session

    async def transaction_exists(self, transaction_id: str) -> bool:
        result = await self.session.execute(
            select(Transaction.transaction_id).where(Transaction.transaction_id == transaction_id)
        )
        return result.scalar_one_or_none() is not None

    async def assessment_status(self, transaction_id: str) -> str | None:
        result = await self.session.execute(
            select(RiskAssessment.status).where(RiskAssessment.transaction_id == transaction_id)
        )
        return cast(str | None, result.scalar_one_or_none())

    async def mark_processing(self, transaction_id: str, attempt: int) -> None:
        result = await self.session.execute(
            select(RiskAssessment).where(RiskAssessment.transaction_id == transaction_id)
        )
        assessment = result.scalar_one_or_none()
        if assessment is None:
            self.session.add(
                RiskAssessment(transaction_id=transaction_id, status="processing", attempts=attempt)
            )
        else:
            assessment.status = "processing"
            assessment.attempts = attempt
        await self.session.flush()

    async def persist_decision(
        self, transaction_id: str, event_id: str, attempt: int, decision: RiskDecision
    ) -> None:
        await persist_risk_result(
            self.session,
            transaction_id=transaction_id,
            event_id=event_id,
            attempt=attempt,
            decision=decision,
        )

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


async def main() -> None:
    """Run the PostgreSQL/Redis-backed risk worker until SIGTERM."""

    client = create_redis_client()
    queue = RedisStreamsQueue(client)
    session_factory = create_session_factory()
    context_provider = VelocityContextProvider(client)
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    async def calculate(event: EventEnvelope[Any]) -> RiskDecision:
        transaction = RiskTransaction.model_validate(
            TransactionReceivedPayload.model_validate(event.payload).model_dump()
        )
        context = await context_provider.get_context(transaction)
        return assess(transaction, context)

    try:
        async with session_factory() as session:
            store = DatabaseWorkerStore(session)
            processor = WorkerProcessor(
                queue,
                store,
                calculate,
                RedisRetryHandler(client),
            )
            await WorkerLoop(queue, processor, consumer="worker-1").run(stop_event)
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
