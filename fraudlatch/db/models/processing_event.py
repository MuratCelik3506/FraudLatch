"""Processing event audit persistence model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fraudlatch.db.base import Base


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

    transaction = relationship("Transaction", back_populates="processing_events")
