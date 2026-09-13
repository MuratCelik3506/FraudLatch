"""Core PostgreSQL persistence models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
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

    risk_assessment: Mapped[RiskAssessment | None] = relationship(
        back_populates="transaction", uselist=False, cascade="all, delete-orphan"
    )
    processing_events: Mapped[list[ProcessingEvent]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan"
    )


class RiskAssessment(Base):
    """Current risk result for one transaction."""

    __tablename__ = "risk_assessments"

    transaction_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("transactions.transaction_id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reasons: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    transaction: Mapped[Transaction] = relationship(back_populates="risk_assessment")


class ProcessingEvent(Base):
    """Append-only processing attempt audit record."""

    __tablename__ = "processing_events"
    __table_args__ = (
        Index("ix_processing_events_transaction_created", "transaction_id", "created_at"),
    )

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("transactions.transaction_id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    transaction: Mapped[Transaction] = relationship(back_populates="processing_events")
