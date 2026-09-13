"""Canonical transaction persistence model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fraudlatch.db.base import Base


class Transaction(Base):
    """Canonical transaction received by the ingestion boundary."""

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_customer_event_time", "customer_id", "event_time"),
        Index("ix_transactions_merchant_event_time", "merchant_id", "event_time"),
    )

    transaction_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    merchant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    source_step: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    risk_assessment = relationship(
        "RiskAssessment", back_populates="transaction", uselist=False, cascade="all, delete-orphan"
    )
    processing_events = relationship(
        "ProcessingEvent", back_populates="transaction", cascade="all, delete-orphan"
    )
