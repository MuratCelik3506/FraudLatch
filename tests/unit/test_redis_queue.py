import asyncio
from typing import Any
from uuid import uuid4

import pytest
from redis.exceptions import ResponseError

from fraudlatch.contracts import EventEnvelope, TransactionReceivedPayload
from fraudlatch.queue import (
    RedisConfigurationError,
    RedisStreamsQueue,
    get_redis_url,
)


def event() -> EventEnvelope[TransactionReceivedPayload]:
    return EventEnvelope[TransactionReceivedPayload](
        event_id=uuid4(),
        event_type="transaction.received",
        schema_version=1,
        occurred_at="2026-01-01T00:00:00Z",
        aggregate_id="txn-1",
        payload=TransactionReceivedPayload(
            transaction_id="txn-1",
            customer_id="customer-1",
            merchant_id="merchant-1",
            category="es_transportation",
            amount="12.34",
            source_step=1,
            event_time="2026-01-01T00:00:00Z",
        ),
    )


class FakeRedis:
    def __init__(self, *, group_exists: bool = False) -> None:
        self.group_exists = group_exists
        self.calls: list[tuple[str, Any]] = []
        self.published_fields: dict[str, str] = {}

    async def xgroup_create(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("xgroup_create", (args, kwargs)))
        if self.group_exists:
            raise ResponseError("BUSYGROUP Consumer Group name already exists")

    async def xadd(self, stream: str, fields: dict[str, str]) -> str:
        self.calls.append(("xadd", (stream, fields)))
        self.published_fields = fields
        return "1-0"

    async def xreadgroup(self, *args: Any, **kwargs: Any) -> list[Any]:
        self.calls.append(("xreadgroup", (args, kwargs)))
        return [(RedisStreamsQueue.stream, [("1-0", self.published_fields)])]

    async def xack(self, *args: Any) -> int:
        self.calls.append(("xack", args))
        return 1

    async def xpending_range(self, *args: Any, **kwargs: Any) -> list[Any]:
        self.calls.append(("xpending_range", (args, kwargs)))
        return [{"message_id": "1-0"}]

    async def xclaim(self, *args: Any) -> list[Any]:
        self.calls.append(("xclaim", args))
        return [("1-0", self.published_fields)]

    async def ping(self) -> bool:
        self.calls.append(("ping", ()))
        return True

    async def aclose(self) -> None:
        self.calls.append(("aclose", ()))


def test_redis_streams_publish_consume_ack_and_reclaim() -> None:
    async def exercise() -> None:
        client = FakeRedis()
        queue = RedisStreamsQueue(client)  # type: ignore[arg-type]

        handle = await queue.publish(event())
        messages = await queue.consume(consumer="worker-1", count=5, block_ms=100)
        reclaimed = await queue.reclaim_pending(consumer="worker-2", min_idle_ms=500)
        await queue.ack(handle)
        await queue.nack(handle, reason="temporary failure")

        assert handle.message_id == "1-0"
        assert len(messages) == 1
        assert messages[0].event.event_type == "transaction.received"
        assert len(reclaimed) == 1
        assert [name for name, _ in client.calls] == [
            "xgroup_create",
            "xadd",
            "xgroup_create",
            "xreadgroup",
            "xpending_range",
            "xclaim",
            "xack",
        ]

    asyncio.run(exercise())


def test_existing_consumer_group_is_accepted_and_healthcheck_closes() -> None:
    async def exercise() -> None:
        client = FakeRedis(group_exists=True)
        queue = RedisStreamsQueue(client)

        await queue.ensure_group()
        assert await queue.healthcheck()
        await queue.close()

    asyncio.run(exercise())


def test_redis_url_requires_supported_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(RedisConfigurationError, match="REDIS_URL must be set"):
        get_redis_url()

    monkeypatch.setenv("REDIS_URL", "http://localhost:6379")
    with pytest.raises(RedisConfigurationError, match="redis://"):
        get_redis_url()
