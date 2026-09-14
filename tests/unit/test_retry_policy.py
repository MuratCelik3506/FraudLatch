import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from fraudlatch.contracts import EventEnvelope, TransactionReceivedPayload
from fraudlatch.queue import (
    RedisRetryHandler,
    RetryPolicy,
    TransientProcessingError,
    classify_processing_error,
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


class FakeRetryRedis:
    def __init__(self, *, fail_dlq: bool = False) -> None:
        self.retry_entries: list[tuple[dict[str, float], str]] = []
        self.dlq_fields: dict[str, str] | None = None
        self.fail_dlq = fail_dlq

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        self.retry_entries.append((mapping, key))
        return 1

    async def xadd(self, stream: str, fields: dict[str, str]) -> str:
        if self.fail_dlq:
            raise ConnectionError("Redis unavailable")
        self.dlq_fields = fields
        return "2-0"


def test_retry_policy_has_three_total_attempts_and_fixed_delays() -> None:
    policy = RetryPolicy()

    first = policy.decide(attempt=1, error_code="dependency_timeout", transient=True)
    second = policy.decide(attempt=2, error_code="dependency_timeout", transient=True)
    third = policy.decide(attempt=3, error_code="dependency_timeout", transient=True)
    permanent = policy.decide(attempt=1, error_code="invalid_event", transient=False)

    assert (first.retry, first.delay_seconds) == (True, 1)
    assert (second.retry, second.delay_seconds) == (True, 5)
    assert (third.retry, third.delay_seconds) == (False, 0)
    assert (permanent.retry, permanent.delay_seconds) == (False, 0)


def test_error_classification_is_stable() -> None:
    assert classify_processing_error(TimeoutError())[0:2] == ("dependency_timeout", True)
    assert classify_processing_error(TransientProcessingError())[0:2] == (
        "dependency_unavailable",
        True,
    )
    assert classify_processing_error(ValueError())[0:2] == ("invalid_event", False)


def test_redis_retry_handler_schedules_and_dead_letters() -> None:
    async def exercise() -> None:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        client = FakeRetryRedis()
        handler = RedisRetryHandler(client)  # type: ignore[arg-type]

        retry = await handler.handle_failure(event(), attempt=1, error=TimeoutError(), now=now)
        terminal = await handler.handle_failure(event(), attempt=3, error=TimeoutError(), now=now)

        assert retry.retry is True
        assert len(client.retry_entries) == 1
        assert next(iter(client.retry_entries[0][0].values())) == now.timestamp() + 1
        assert terminal.retry is False
        assert client.dlq_fields is not None
        assert client.dlq_fields["attempts"] == "3"
        assert client.dlq_fields["error_code"] == "dependency_timeout"

    asyncio.run(exercise())


def test_dlq_failure_is_not_swallowed() -> None:
    async def exercise() -> None:
        handler = RedisRetryHandler(FakeRetryRedis(fail_dlq=True))  # type: ignore[arg-type]
        with pytest.raises(ConnectionError):
            await handler.handle_failure(event(), attempt=3, error=TimeoutError())

    asyncio.run(exercise())
