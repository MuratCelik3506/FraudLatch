"""Validated configuration for deterministic rules-v1."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RulesConfig(BaseModel):
    """Thresholds and rule weights used by the pure risk engine."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    global_amount_threshold: Decimal = Field(default=Decimal("1000"), gt=0)
    category_amount_thresholds: dict[str, Decimal] = Field(default_factory=dict)
    customer_velocity_threshold: int = Field(default=5, ge=1)
    merchant_velocity_threshold: int = Field(default=20, ge=1)
    category_risk_weights: dict[str, Decimal] = Field(default_factory=dict)
    high_amount_weight: Decimal = Field(default=Decimal("0.35"), ge=0, le=1)
    customer_velocity_weight: Decimal = Field(default=Decimal("0.25"), ge=0, le=1)
    merchant_velocity_weight: Decimal = Field(default=Decimal("0.20"), ge=0, le=1)
    amount_deviation_multiplier: Decimal = Field(default=Decimal("3"), gt=0)
    amount_deviation_weight: Decimal = Field(default=Decimal("0.20"), ge=0, le=1)
    amount_deviation_min_samples: int = Field(default=2, ge=2)

    @field_validator("category_amount_thresholds")
    @classmethod
    def validate_amount_thresholds(cls, values: dict[str, Decimal]) -> dict[str, Decimal]:
        if any(value <= 0 for value in values.values()):
            raise ValueError("category amount thresholds must be positive")
        return values

    @field_validator("category_risk_weights")
    @classmethod
    def validate_category_weights(cls, values: dict[str, Decimal]) -> dict[str, Decimal]:
        if any(value < 0 or value > 1 for value in values.values()):
            raise ValueError("category risk weights must be between 0 and 1")
        return values
