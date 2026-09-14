"""Bounded retry and dead-letter handling for queue events."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError

from fraudlatch.contracts import EventEnvelope, UnsupportedEventVersionError, serialize_event


class TransientProcessingError(Exception):
    """A dependency or timeout failure that may succeed on a later attempt."""

    code = "transient_processing_error"


class PermanentProcessingError(Exception):
    """A malformed or otherwise non-retryable event failure."""

    code = "permanent_processing_error"


class RetryDecision(BaseModel):
    """Deterministic outcome for one failed processing attempt."""

    model_config = ConfigDict(frozen=True)

    attempt: int = Field(ge=1)
    error_code: str = Field(min_length=1)
    retry: bool
    delay_seconds: int = Field(ge=0)


class RetryPolicy:
    """Three-attempt policy with fixed delays before attempts two and three."""

    max_attempts = 3
    retry_delays_seconds = (1, 5)

    def decide(self, *, attempt: int, error_code: str, transient: bool) -> RetryDecision:
        if attempt < 1 or attempt > self.max_attempts:
            raise ValueError("attempt must be between 1 and 3")
        should_retry = transient and attempt < self.max_attempts
        delay = self.retry_delays_seconds[attempt - 1] if should_retry else 0
        return RetryDecision(
            attempt=attempt,
            error_code=error_code,
            retry=should_retry,
            delay_seconds=delay,
        )


def classify_processing_error(error: BaseException) -> tuple[str, bool]:
    """Return a stable error code and whether the failure is transient."""

    if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
        return "dependency_timeout", True
    if isinstance(error, (ConnectionError, RedisError, TransientProcessingError)):
        return "dependency_unavailable", True
    if isinstance(error, UnsupportedEventVersionError):
        return UnsupportedEventVersionError.code, False
    if isinstance(error, (PermanentProcessingError, ValueError)):
        return "invalid_event", False
    return "processing_error", False


class RetryMetrics(Protocol):
    """Optional metrics sink for retry and DLQ counters."""

    def retry_scheduled(self, error_code: str) -> None:
        """Record a scheduled retry."""

    def dead_lettered(self, error_code: str) -> None:
        """Record a dead-lettered event."""


class NullRetryMetrics:
    """No-op metrics sink used when observability is not configured."""

    def retry_scheduled(self, error_code: str) -> None:
        pass

    def dead_lettered(self, error_code: str) -> None:
        pass


class RedisRetryHandler:
    """Persist retry schedule entries and terminal failures in Redis."""

    retry_key = "fraudlatch:transactions:retry:v1"
    dlq_stream = "fraudlatch:transactions:dlq:v1"

    def __init__(
        self,
        client: Redis,
        *,
        policy: RetryPolicy | None = None,
        metrics: RetryMetrics | None = None,
    ) -> None:
        self.client = client
        self.policy = policy or RetryPolicy()
        self.metrics = metrics or NullRetryMetrics()

    async def handle_failure(
        self,
        event: EventEnvelope[Any],
        *,
        attempt: int,
        error: BaseException,
        now: datetime | None = None,
    ) -> RetryDecision:
        """Schedule a retry or durably publish to the DLQ."""

        error_code, transient = classify_processing_error(error)
        decision = self.policy.decide(attempt=attempt, error_code=error_code, transient=transient)
        if decision.retry:
            await self.schedule_retry(event, decision, now=now)
            self.metrics.retry_scheduled(decision.error_code)
        else:
            await self.publish_dlq(event, decision, now=now)
            self.metrics.dead_lettered(decision.error_code)
        return decision

    async def schedule_retry(
        self,
        event: EventEnvelope[Any],
        decision: RetryDecision,
        *,
        now: datetime | None = None,
    ) -> None:
        """Store a retry envelope in a sorted set until its due time."""

        timestamp = (now or datetime.now(UTC)) + timedelta(seconds=decision.delay_seconds)
        record = json.dumps(
            {
                "envelope": serialize_event(event),
                "attempt": decision.attempt + 1,
                "error_code": decision.error_code,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        await self.client.zadd(self.retry_key, {record: timestamp.timestamp()})

    async def publish_dlq(
        self,
        event: EventEnvelope[Any],
        decision: RetryDecision,
        *,
        now: datetime | None = None,
    ) -> str:
        """Publish the original envelope and failure metadata to the DLQ."""

        fields = {
            "envelope": serialize_event(event),
            "attempts": str(decision.attempt),
            "error_code": decision.error_code,
            "failed_at": (now or datetime.now(UTC)).isoformat(),
        }
        message_id = await self.client.xadd(self.dlq_stream, cast(Any, fields))
        return str(message_id)


def retry_record_fields(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a scheduled retry record for a publisher."""

    if not record.get("envelope") or not record.get("attempt"):
        raise ValueError("invalid_retry_record")
    return {
        "envelope": str(record["envelope"]),
        "attempt": int(record["attempt"]),
        "error_code": str(record.get("error_code", "unknown")),
    }
