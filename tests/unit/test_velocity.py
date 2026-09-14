import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from fraudlatch.risk import RiskTransaction, VelocityContextProvider


def transaction(**changes: object) -> RiskTransaction:
    values: dict[str, object] = {
        "transaction_id": "txn-1",
        "customer_id": "customer-1",
        "merchant_id": "merchant-1",
        "category": "es_food",
        "amount": "12.34",
        "source_step": 1,
        "source": "api",
        "event_time": "2026-01-01T12:00:00Z",
    }
    values.update(changes)
    return RiskTransaction(**values)


class FakeSortedSets:
    def __init__(self) -> None:
        self.data: dict[str, dict[str, float]] = {}
        self.expirations: dict[str, int] = {}

    async def zremrangebyscore(self, key: str, minimum: str, maximum: float) -> int:
        del minimum
        entries = self.data.setdefault(key, {})
        removed = [member for member, score in entries.items() if score <= maximum]
        for member in removed:
            del entries[member]
        return len(removed)

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        self.data.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def expire(self, key: str, seconds: int) -> bool:
        self.expirations[key] = seconds
        return True

    async def zcount(self, key: str, minimum: float, maximum: float) -> int:
        return sum(minimum <= score <= maximum for score in self.data.get(key, {}).values())

    async def zrange(self, key: str, start: int, stop: int, *, withscores: bool) -> list[Any]:
        del start, stop, withscores
        rows = sorted(self.data.get(key, {}).items(), key=lambda item: item[1])
        return rows[-1:] if rows else []


def test_velocity_uses_event_time_and_separates_customer_and_merchant() -> None:
    async def exercise() -> None:
        client = FakeSortedSets()
        provider = VelocityContextProvider(client)  # type: ignore[arg-type]
        current = datetime(2026, 1, 1, 12, tzinfo=UTC)
        customer_key = provider.customer_key("customer-1")
        merchant_key = provider.merchant_key("merchant-1")
        client.data[customer_key] = {
            "old": (current - timedelta(minutes=6)).timestamp(),
            "recent": (current - timedelta(minutes=2)).timestamp(),
        }
        client.data[merchant_key] = {
            "merchant-recent": (current - timedelta(minutes=2)).timestamp(),
        }

        context = await provider.get_context(transaction(), now=current)

        assert (context.customer_velocity, context.merchant_velocity) == (2, 2)
        assert context.latest_customer_event_time == current
        assert context.latest_merchant_event_time == current
        assert client.expirations[customer_key] == 600
        assert "old" not in client.data[customer_key]

    asyncio.run(exercise())


def test_cold_start_is_zero_and_duplicate_transaction_is_idempotent() -> None:
    async def exercise() -> None:
        client = FakeSortedSets()
        provider = VelocityContextProvider(client)
        current = datetime(2026, 1, 1, 12, tzinfo=UTC)

        first = await provider.get_context(transaction(), now=current)
        second = await provider.get_context(transaction(), now=current)

        assert first.customer_velocity == 1
        assert first.merchant_velocity == 1
        assert second == first

    asyncio.run(exercise())


def test_future_event_time_is_rejected_before_state_mutation() -> None:
    async def exercise() -> None:
        client = FakeSortedSets()
        provider = VelocityContextProvider(client)
        current = datetime(2026, 1, 1, 12, tzinfo=UTC)
        with pytest.raises(ValueError, match="future"):
            await provider.get_context(transaction(event_time="2026-01-01T12:01:00Z"), now=current)
        assert client.data == {}

    asyncio.run(exercise())


def test_redis_failure_is_propagated() -> None:
    async def exercise() -> None:
        class BrokenRedis(FakeSortedSets):
            async def zremrangebyscore(self, key: str, minimum: str, maximum: float) -> int:
                raise ConnectionError("Redis unavailable")

        provider = VelocityContextProvider(BrokenRedis())
        current = datetime(2026, 1, 1, 12, tzinfo=UTC)
        with pytest.raises(ConnectionError, match="unavailable"):
            await provider.get_context(transaction(), now=current)

    asyncio.run(exercise())
