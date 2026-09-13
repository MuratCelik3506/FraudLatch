"""Async transaction repository operations."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fraudlatch.api.schemas import TransactionIn
from fraudlatch.db.models import OutboxEvent, Transaction


def transaction_values(transaction: TransactionIn) -> dict[str, object]:
    """Return the canonical fields used for idempotency comparison."""

    return transaction.model_dump()


async def get_transaction(session: AsyncSession, transaction_id: str) -> Transaction | None:
    """Fetch a transaction by its stable external identifier."""

    result = await session.execute(
        select(Transaction).where(Transaction.transaction_id == transaction_id)
    )
    return result.scalar_one_or_none()


async def create_transaction(session: AsyncSession, payload: TransactionIn) -> Transaction:
    """Persist a new canonical transaction without publishing an event."""

    transaction = Transaction(**transaction_values(payload))
    session.add(transaction)
    await session.flush()
    return transaction


async def create_outbox_event(session: AsyncSession, payload: TransactionIn) -> OutboxEvent:
    """Persist the initial transaction-received event in the same DB transaction."""

    event = OutboxEvent(
        event_id=str(uuid4()),
        event_type="transaction.received",
        schema_version=1,
        occurred_at=payload.event_time,
        aggregate_id=payload.transaction_id,
        payload=payload.model_dump(mode="json"),
        status="pending",
        attempts=0,
    )
    session.add(event)
    await session.flush()
    return event


def matches_payload(existing: Transaction, payload: TransactionIn) -> bool:
    """Compare an existing row with a retry payload."""

    values = transaction_values(payload)
    return all(getattr(existing, field) == value for field, value in values.items())
