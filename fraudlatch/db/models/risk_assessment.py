"""Current risk assessment persistence model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fraudlatch.db.base import Base


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

    transaction = relationship("Transaction", back_populates="risk_assessment")
