"""Redis Streams implementation of the queue contract."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from fraudlatch.contracts import deserialize_event, serialize_event
from fraudlatch.queue.ports import MessageHandle, QueueMessage, QueuePort


class RedisConfigurationError(ValueError):
    """Raised when Redis configuration is missing or incompatible."""


def get_redis_url() -> str:
    """Return and validate the configured Redis URL."""

    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        raise RedisConfigurationError("REDIS_URL must be set")
    if not url.startswith(("redis://", "rediss://")):
        raise RedisConfigurationError("REDIS_URL must use redis:// or rediss://")
    return url


def create_redis_client(redis_url: str | None = None) -> Redis:
    """Create a Redis client with text responses for stream fields."""

    return cast(Redis, Redis.from_url(redis_url or get_redis_url(), decode_responses=True))


class RedisStreamsQueue(QueuePort):
    """Queue adapter backed by one Redis stream and consumer group."""

    stream = "fraudlatch:transactions:v1"
    group = "risk-workers"

    def __init__(self, client: Redis, *, stream: str = stream, group: str = group) -> None:
        self.client = client
        self.stream_name = stream
        self.group_name = group

    async def ensure_group(self) -> None:
        """Create the consumer group, treating an existing group as success."""

        try:
            await self.client.xgroup_create(
                self.stream_name, self.group_name, id="0-0", mkstream=True
            )
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    async def publish(self, event: Any) -> MessageHandle:
        """Publish a serialized envelope to the main stream."""

        await self.ensure_group()
        message_id = await self.client.xadd(
            self.stream_name,
            {"envelope": serialize_event(event), "attempts": "0"},
        )
        return MessageHandle(queue=self.stream_name, message_id=str(message_id))

    async def consume(
        self,
        *,
        consumer: str,
        count: int = 1,
        block_ms: int | None = None,
    ) -> Sequence[QueueMessage]:
        """Read a batch of new messages for a named consumer."""

        if not consumer:
            raise ValueError("consumer must not be empty")
        if count < 1:
            raise ValueError("count must be positive")
        await self.ensure_group()
        rows = await self.client.xreadgroup(
            self.group_name,
            consumer,
            {self.stream_name: ">"},
            count=count,
            block=block_ms,
        )
        return self._message_list(rows)

    async def ack(self, handle: MessageHandle) -> None:
        """Acknowledge only the exact Redis stream message ID."""

        self._validate_handle(handle)
        await self.client.xack(self.stream_name, self.group_name, handle.message_id)

    async def nack(self, handle: MessageHandle, *, reason: str) -> None:
        """Leave a failed message pending for the retry policy to handle."""

        self._validate_handle(handle)
        if not reason:
            raise ValueError("reason must not be empty")

    async def reclaim_pending(
        self, *, consumer: str, min_idle_ms: int = 1_000, count: int = 100
    ) -> Sequence[QueueMessage]:
        """Claim stale pending entries after a consumer restart."""

        if min_idle_ms < 0:
            raise ValueError("min_idle_ms must not be negative")
        pending = await self.client.xpending_range(
            self.stream_name,
            self.group_name,
            min="-",
            max="+",
            count=count,
            idle=min_idle_ms,
        )
        message_ids: list[int | bytes | str | memoryview[int]] = [
            str(entry["message_id"]) for entry in pending
        ]
        if not message_ids:
            return []
        rows = await self.client.xclaim(
            self.stream_name,
            self.group_name,
            consumer,
            min_idle_ms,
            message_ids,
        )
        return self._message_list([(self.stream_name, rows)])

    async def healthcheck(self) -> bool:
        """Return whether Redis responds to a ping."""

        return bool(await self.client.ping())

    async def close(self) -> None:
        """Close the underlying async Redis client."""

        await self.client.aclose()

    def _validate_handle(self, handle: MessageHandle) -> None:
        if handle.queue != self.stream_name:
            raise ValueError("message handle belongs to a different queue")

    def _message_list(
        self, rows: Sequence[tuple[str, Sequence[tuple[str, Mapping[str, Any]]]]]
    ) -> list[QueueMessage]:
        messages: list[QueueMessage] = []
        for stream_name, stream_messages in rows:
            if stream_name != self.stream_name:
                continue
            for message_id, fields in stream_messages:
                raw_payload = str(fields["envelope"])
                messages.append(
                    QueueMessage(
                        handle=MessageHandle(queue=self.stream_name, message_id=str(message_id)),
                        event=deserialize_event(raw_payload),
                        raw_payload=raw_payload,
                        attempts=max(1, int(fields.get("attempts", 1))),
                    )
                )
        return messages
