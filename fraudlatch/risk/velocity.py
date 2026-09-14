"""Redis Sorted Set backed velocity context provider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from redis.asyncio import Redis

from fraudlatch.risk.models import RiskContext, RiskTransaction


class VelocityContextProvider:
    """Maintain bounded customer and merchant event-time windows."""

    customer_prefix = "fraudlatch:velocity:customer:"
    merchant_prefix = "fraudlatch:velocity:merchant:"

    def __init__(
        self,
        client: Redis,
        *,
        window: timedelta = timedelta(minutes=5),
        ttl_seconds: int = 600,
    ) -> None:
        if window.total_seconds() <= 0:
            raise ValueError("window must be positive")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.client = client
        self.window = window
        self.ttl_seconds = ttl_seconds

    @classmethod
    def customer_key(cls, customer_id: str) -> str:
        return f"{cls.customer_prefix}{customer_id}"

    @classmethod
    def merchant_key(cls, merchant_id: str) -> str:
        return f"{cls.merchant_prefix}{merchant_id}"

    async def get_context(
        self, transaction: RiskTransaction, *, now: datetime | None = None
    ) -> RiskContext:
        """Record the event and return both five-minute velocity counts."""

        current_time = now or datetime.now(UTC)
        self._validate_event_time(transaction.event_time, current_time)
        cutoff = transaction.event_time - self.window
        customer_key = self.customer_key(transaction.customer_id)
        merchant_key = self.merchant_key(transaction.merchant_id)
        score = transaction.event_time.timestamp()
        cutoff_score = cutoff.timestamp()

        for key in (customer_key, merchant_key):
            await self.client.zremrangebyscore(key, "-inf", cutoff_score)
            await self.client.zadd(key, cast(Any, {transaction.transaction_id: score}))
            await self.client.expire(key, self.ttl_seconds)

        customer_count = await self.client.zcount(customer_key, cutoff_score, score)
        merchant_count = await self.client.zcount(merchant_key, cutoff_score, score)
        return RiskContext(
            customer_velocity=int(customer_count),
            merchant_velocity=int(merchant_count),
            latest_customer_event_time=await self._latest_time(customer_key),
            latest_merchant_event_time=await self._latest_time(merchant_key),
        )

    async def _latest_time(self, key: str) -> datetime | None:
        rows = await self.client.zrange(key, -1, -1, withscores=True)
        if not rows:
            return None
        return datetime.fromtimestamp(float(rows[0][1]), tz=UTC)

    @staticmethod
    def _validate_event_time(event_time: datetime, now: datetime) -> None:
        if event_time.tzinfo is None or event_time.utcoffset() is None:
            raise ValueError("event_time must be timezone-aware")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if event_time > now:
            raise ValueError("event_time cannot be in the future")
