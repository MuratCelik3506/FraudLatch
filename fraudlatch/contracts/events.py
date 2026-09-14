"""Versioned domain event contracts."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class UnsupportedEventVersionError(ValueError):
    """Raised when an event type is sent with an unsupported schema version."""

    code = "unsupported_schema_version"

    def __init__(self, event_type: str, schema_version: int) -> None:
        super().__init__(f"{self.code}: {event_type} v{schema_version}")


class TransactionReceivedPayload(BaseModel):
    """Schema version 1 payload for a transaction.received event."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(min_length=1, max_length=128)
    customer_id: str = Field(min_length=1, max_length=128)
    merchant_id: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=128)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    source_step: int = Field(ge=0)
    source: str = Field(default="api", min_length=1, max_length=64)
    event_time: datetime
    source_metadata: dict[str, Any] | None = None

    @field_validator("event_time")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event_time must be timezone-aware")
        return value


class EventEnvelope[T: BaseModel](BaseModel):
    """Transport-neutral envelope for at-least-once domain events."""

    model_config = ConfigDict(extra="forbid")

    SUPPORTED_VERSIONS: ClassVar[dict[str, frozenset[int]]] = {
        "transaction.received": frozenset({1}),
    }

    event_id: UUID
    event_type: str = Field(min_length=1, max_length=128)
    schema_version: int = Field(gt=0)
    occurred_at: datetime
    aggregate_id: str = Field(min_length=1, max_length=128)
    payload: T

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_schema_version(self) -> EventEnvelope[T]:
        supported = self.SUPPORTED_VERSIONS.get(self.event_type)
        if supported is None or self.schema_version not in supported:
            raise UnsupportedEventVersionError(self.event_type, self.schema_version)
        return self


def serialize_event(event: EventEnvelope[BaseModel]) -> str:
    """Serialize an event without losing its versioned payload."""

    return event.model_dump_json()


def deserialize_event(raw_payload: str) -> EventEnvelope[Any]:
    """Deserialize a supported event using its registered payload model."""

    event_data = json.loads(raw_payload)
    if not isinstance(event_data, dict):
        raise ValueError("invalid_event_payload: expected an object")
    event_type = event_data.get("event_type")
    schema_version = event_data.get("schema_version")
    if event_type == "transaction.received" and schema_version == 1:
        return EventEnvelope[TransactionReceivedPayload].model_validate_json(raw_payload)
    raise UnsupportedEventVersionError(str(event_type), int(schema_version or 0))
