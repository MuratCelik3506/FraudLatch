from datetime import datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from fraudlatch.contracts import EventEnvelope, TransactionReceivedPayload


def valid_event() -> EventEnvelope[TransactionReceivedPayload]:
    payload = TransactionReceivedPayload(
        transaction_id="txn-1",
        customer_id="customer-1",
        merchant_id="merchant-1",
        category="es_transportation",
        amount="12.34",
        source_step=1,
        event_time="2026-01-01T00:00:00Z",
    )
    return EventEnvelope[TransactionReceivedPayload](
        event_id=uuid4(),
        event_type="transaction.received",
        schema_version=1,
        occurred_at="2026-01-01T00:00:00Z",
        aggregate_id="txn-1",
        payload=payload,
    )


def test_event_envelope_round_trips_without_information_loss() -> None:
    event = valid_event()

    decoded = EventEnvelope[TransactionReceivedPayload].model_validate_json(event.model_dump_json())

    assert decoded == event
    assert isinstance(decoded.event_id, UUID)
    assert decoded.payload.amount == event.payload.amount


def test_event_envelope_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError, match="occurred_at must be timezone-aware"):
        EventEnvelope[TransactionReceivedPayload](
            event_id=uuid4(),
            event_type="transaction.received",
            schema_version=1,
            occurred_at=datetime(2026, 1, 1),
            aggregate_id="txn-1",
            payload=valid_event().payload,
        )


def test_event_envelope_rejects_unsupported_schema_version() -> None:
    with pytest.raises(ValidationError, match="unsupported_schema_version"):
        EventEnvelope[TransactionReceivedPayload](
            event_id=uuid4(),
            event_type="transaction.received",
            schema_version=2,
            occurred_at="2026-01-01T00:00:00Z",
            aggregate_id="txn-1",
            payload=valid_event().payload,
        )


def test_event_envelope_rejects_unknown_event_type_and_extra_fields() -> None:
    with pytest.raises(ValidationError, match="unsupported_schema_version"):
        EventEnvelope[TransactionReceivedPayload](
            event_id=uuid4(),
            event_type="transaction.unknown",
            schema_version=1,
            occurred_at="2026-01-01T00:00:00Z",
            aggregate_id="txn-1",
            payload=valid_event().payload,
        )

    data = valid_event().model_dump()
    data["unexpected"] = True
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EventEnvelope[TransactionReceivedPayload].model_validate(data)
