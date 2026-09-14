"""Pydantic request and response contracts for transaction ingestion."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TransactionIn(BaseModel):
    """Canonical transaction accepted by the API."""

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


class TransactionResponse(TransactionIn):
    """Persisted transaction returned by query endpoints."""

    model_config = ConfigDict(from_attributes=True)
    created_at: datetime


class TransactionAccepted(BaseModel):
    """Acknowledgement returned after durable transaction acceptance."""

    transaction_id: str
    status: str


class RiskAssessmentResponse(BaseModel):
    """Public representation of the current risk assessment."""

    model_config = ConfigDict(from_attributes=True)

    transaction_id: str
    status: str
    score: Decimal | None = None
    level: str | None = None
    reasons: list[dict[str, Any]] | None = None
    engine_version: str | None = None
    attempts: int
    error_code: str | None = None
    updated_at: datetime


class HighRiskResponse(BaseModel):
    """Bounded page of high-risk assessments."""

    items: list[RiskAssessmentResponse]
    limit: int
    offset: int
