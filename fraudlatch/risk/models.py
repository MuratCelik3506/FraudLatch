"""Input, context, and output models for rules-v1."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ReasonCode = Literal["HIGH_AMOUNT", "CUSTOMER_VELOCITY", "MERCHANT_VELOCITY", "CATEGORY_RISK"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]


class RiskTransaction(BaseModel):
    """Canonical transaction fields available to the pure scorer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    transaction_id: str = Field(min_length=1, max_length=128)
    customer_id: str = Field(min_length=1, max_length=128)
    merchant_id: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=128)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    source_step: int = Field(ge=0)
    source: str = Field(min_length=1, max_length=64)
    event_time: datetime
    source_metadata: dict[str, Any] | None = None

    @field_validator("event_time")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event_time must be timezone-aware")
        return value


class RiskContext(BaseModel):
    """Optional live context supplied by providers such as Redis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    customer_velocity: int = Field(default=0, ge=0)
    merchant_velocity: int = Field(default=0, ge=0)
    latest_customer_event_time: datetime | None = None
    latest_merchant_event_time: datetime | None = None

    @field_validator("latest_customer_event_time", "latest_merchant_event_time")
    @classmethod
    def require_context_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("context event times must be timezone-aware")
        return value


class RiskReason(BaseModel):
    """One explainable rule contribution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: ReasonCode
    contribution: Decimal = Field(ge=0, le=1, max_digits=5, decimal_places=4)


class RiskDecision(BaseModel):
    """Stable, explainable output of rules-v1."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    risk_score: Decimal = Field(ge=0, le=1, max_digits=5, decimal_places=4)
    risk_level: RiskLevel
    reasons: tuple[RiskReason, ...]
    engine_version: Literal["rules-v1"] = "rules-v1"
