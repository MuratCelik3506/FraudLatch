from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from fraudlatch.api.app import create_app
from fraudlatch.api.schemas import TransactionIn


def valid_payload() -> dict[str, object]:
    return {
        "transaction_id": "txn-1",
        "customer_id": "customer-1",
        "merchant_id": "merchant-1",
        "category": "es_transportation",
        "amount": "12.34",
        "source_step": 1,
        "event_time": "2026-01-01T00:00:00Z",
    }


def test_transaction_input_rejects_ground_truth_label() -> None:
    with pytest.raises(ValidationError):
        TransactionIn(**valid_payload(), is_fraud=False)


def test_transaction_input_requires_positive_amount_and_timezone() -> None:
    payload = valid_payload()
    payload["amount"] = Decimal("0")
    with pytest.raises(ValidationError):
        TransactionIn(**payload)

    payload = valid_payload()
    payload["event_time"] = datetime(2026, 1, 1)
    with pytest.raises(ValidationError):
        TransactionIn(**payload)


def test_health_is_liveness_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
    app = create_app(session_factory=None)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
