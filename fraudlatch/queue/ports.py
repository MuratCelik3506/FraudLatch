"""Technology-independent queue interfaces."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from fraudlatch.contracts.events import EventEnvelope


class MessageHandle(BaseModel):
    """Opaque identity required to acknowledge or reject a queue message."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    queue: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=256)


class QueueMessage(BaseModel):
    """A received event and its adapter-specific acknowledgement handle."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    handle: MessageHandle
    event: EventEnvelope[Any]
    raw_payload: str = Field(min_length=1)


class QueuePort(Protocol):
    """Minimal queue contract implemented by Redis and future adapters."""

    async def publish(self, event: EventEnvelope[Any]) -> MessageHandle:
        """Publish an event and return its adapter-specific handle."""

    async def consume(
        self,
        *,
        consumer: str,
        count: int = 1,
        block_ms: int | None = None,
    ) -> Sequence[QueueMessage]:
        """Read available messages without deciding their business outcome."""

    async def ack(self, handle: MessageHandle) -> None:
        """Acknowledge successful processing of a message."""

    async def nack(self, handle: MessageHandle, *, reason: str) -> None:
        """Reject a message while leaving retry/DLQ policy to the adapter."""
