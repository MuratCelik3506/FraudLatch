import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from fraudlatch.api.app import create_app
from fraudlatch.db.models import OutboxEvent

pytestmark = pytest.mark.integration


def payload(transaction_id: str = "txn-integration-1") -> dict[str, object]:
    return {
        "transaction_id": transaction_id,
        "customer_id": "customer-1",
        "merchant_id": "merchant-1",
        "category": "es_transportation",
        "amount": "12.34",
        "source_step": 1,
        "event_time": "2026-01-01T00:00:00Z",
    }


@pytest.mark.anyio
async def test_ingestion_is_idempotent_and_detects_conflicts() -> None:
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        accepted = await client.post("/v1/transactions", json=payload())
        duplicate = await client.post("/v1/transactions", json=payload())
        conflict_payload = payload()
        conflict_payload["amount"] = "99.99"
        conflict = await client.post("/v1/transactions", json=conflict_payload)
        queried = await client.get("/v1/transactions/txn-integration-1")

    async with app.state.session_factory() as session:
        outbox_count = await session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.aggregate_id == "txn-integration-1")
        )

    assert accepted.status_code == 202
    assert accepted.json()["status"] == "accepted"
    assert duplicate.status_code == 202
    assert duplicate.json()["status"] == "already_accepted"
    assert conflict.status_code == 409
    assert queried.status_code == 200
    assert queried.json()["amount"] == "12.34"
    assert outbox_count == 1
