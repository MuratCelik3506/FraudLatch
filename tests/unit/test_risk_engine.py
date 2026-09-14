from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from fraudlatch.risk import RiskContext, RiskTransaction, RulesConfig, assess


def transaction(**changes: object) -> RiskTransaction:
    values: dict[str, object] = {
        "transaction_id": "txn-1",
        "customer_id": "customer-1",
        "merchant_id": "merchant-1",
        "category": "es_transportation",
        "amount": "12.34",
        "source_step": 1,
        "source": "api",
        "event_time": "2026-01-01T00:00:00Z",
    }
    values.update(changes)
    return RiskTransaction(**values)


def test_each_rule_is_explainable_and_reasons_are_ordered() -> None:
    decision = assess(
        transaction(amount="1500"),
        RiskContext(customer_velocity=5, merchant_velocity=20),
        RulesConfig(category_risk_weights={"es_transportation": Decimal("0.20")}),
    )

    assert [reason.code for reason in decision.reasons] == [
        "HIGH_AMOUNT",
        "CUSTOMER_VELOCITY",
        "MERCHANT_VELOCITY",
        "CATEGORY_RISK",
    ]
    assert decision.risk_score == Decimal("1.0000")
    assert decision.risk_level == "HIGH"
    assert decision.engine_version == "rules-v1"


def test_boundaries_and_cold_start_are_deterministic() -> None:
    config = RulesConfig(
        global_amount_threshold=Decimal("100"),
        high_amount_weight=Decimal("0.40"),
    )
    medium = assess(transaction(amount="100"), config=config)
    low = assess(transaction(amount="99.99"), config=config)
    repeated = assess(transaction(amount="100"), config=config)

    assert (medium.risk_score, medium.risk_level) == (Decimal("0.4000"), "MEDIUM")
    assert (low.risk_score, low.risk_level) == (Decimal("0.0000"), "LOW")
    assert medium == repeated
    assert assess(transaction()) == assess(transaction(), RiskContext())


def test_category_amount_threshold_overrides_global_threshold() -> None:
    decision = assess(
        transaction(category="es_food", amount="75"),
        config=RulesConfig(
            global_amount_threshold=Decimal("100"),
            category_amount_thresholds={"es_food": Decimal("50")},
        ),
    )

    assert [reason.code for reason in decision.reasons] == ["HIGH_AMOUNT"]


def test_invalid_configuration_and_naive_time_fail_explicitly() -> None:
    with pytest.raises(ValidationError):
        RulesConfig(customer_velocity_threshold=0)
    with pytest.raises(ValidationError):
        RulesConfig(category_risk_weights={"bad": Decimal("1.1")})
    with pytest.raises(ValidationError, match="timezone-aware"):
        RiskTransaction(
            transaction_id="txn-1",
            customer_id="customer-1",
            merchant_id="merchant-1",
            category="es_food",
            amount="1",
            source_step=0,
            source="api",
            event_time=datetime(2026, 1, 1, tzinfo=None),
        )
