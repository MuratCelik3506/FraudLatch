from datetime import UTC, datetime

import pytest
from sqlalchemy import DateTime, Numeric

from fraudlatch.db.config import DatabaseConfigurationError, get_database_url
from fraudlatch.db.models import RiskAssessment, Transaction


def test_database_url_requires_async_postgresql(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
    assert get_database_url().startswith("postgresql+asyncpg://")

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    with pytest.raises(DatabaseConfigurationError):
        get_database_url()


def test_transaction_columns_preserve_precision_and_timezone() -> None:
    amount = Transaction.__table__.c.amount.type
    event_time = Transaction.__table__.c.event_time.type

    assert isinstance(amount, Numeric)
    assert (amount.precision, amount.scale) == (18, 2)
    assert isinstance(event_time, DateTime)
    assert event_time.timezone is True
    assert datetime.now(UTC).tzinfo is not None


def test_risk_assessment_is_one_row_per_transaction() -> None:
    assert list(RiskAssessment.__table__.primary_key.columns.keys()) == ["transaction_id"]
