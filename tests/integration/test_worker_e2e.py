import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from fraudlatch.api.app import create_app
from fraudlatch.db.session import create_session_factory
from fraudlatch.dispatcher import OutboxDispatcher
from fraudlatch.queue import RedisRetryHandler, RedisStreamsQueue
from fraudlatch.risk import assess
from fraudlatch.risk.models import RiskTransaction
from fraudlatch.risk.velocity import VelocityContextProvider
from fraudlatch.worker import DatabaseWorkerStore, WorkerProcessor

pytestmark = pytest.mark.integration


@pytest.mark.anyio
async def test_submit_dispatch_process_and_query_risk() -> None:
    transaction_id = f"e2e-{uuid4()}"
    session_factory = create_session_factory()
    app = create_app(session_factory=session_factory)
    payload = {
        "transaction_id": transaction_id,
        "customer_id": "e2e-customer",
        "merchant_id": "e2e-merchant",
        "category": "es_transportation",
        "amount": "12.34",
        "source_step": 1,
        "event_time": "2026-01-01T00:00:00Z",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/transactions", json=payload)
    assert response.status_code == 202

    redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    queue = RedisStreamsQueue(redis, stream=f"e2e:{transaction_id}", group="e2e-workers")
    try:
        async with session_factory() as session:
            await OutboxDispatcher(session_factory, queue).dispatch_once()
            messages = await queue.consume(consumer="e2e-1", count=100, block_ms=1000)
            message = next(
                (
                    candidate
                    for candidate in messages
                    if candidate.event.aggregate_id == transaction_id
                ),
                None,
            )
            assert message is not None
            store = DatabaseWorkerStore(session)
            velocity = VelocityContextProvider(redis)

            async def calculate(event: object):
                transaction = RiskTransaction.model_validate(event.payload.model_dump())  # type: ignore[union-attr]
                return assess(
                    transaction, await velocity.get_context(transaction, now=transaction.event_time)
                )

            processor = WorkerProcessor(queue, store, calculate, RedisRetryHandler(redis))  # type: ignore[arg-type]
            assert await processor.process(message)
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            risk = await client.get(f"/v1/transactions/{transaction_id}/risk")
        assert risk.status_code == 200
        assert risk.json()["status"] == "completed"
    finally:
        await redis.delete(queue.stream_name)
        await redis.aclose()
