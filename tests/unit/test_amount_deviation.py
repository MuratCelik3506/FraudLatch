from decimal import Decimal

import pytest
from pydantic import ValidationError

from fraudlatch.risk import (
    AmountBaseline,
    AmountDeviationContextProvider,
    RiskContext,
    RiskTransaction,
    assess,
    build_amount_baselines,
)


def transaction(identifier: str, amount: str, customer_id: str = "customer-1") -> RiskTransaction:
    return RiskTransaction(
        transaction_id=identifier,
        customer_id=customer_id,
        merchant_id="merchant-1",
        category="es_food",
        amount=amount,
        source_step=1,
        source="api",
        event_time=f"2026-01-01T12:0{identifier[-1]}:00Z",
    )


def test_baselines_are_deterministic_and_ignore_input_order() -> None:
    records = [transaction("txn-3", "30"), transaction("txn-1", "10"), transaction("txn-2", "20")]

    first = build_amount_baselines(records)
    second = build_amount_baselines(reversed(records))

    assert first == second
    assert first["customer-1"].sample_count == 3
    assert first["customer-1"].mean == Decimal("20")
    assert first["customer-1"].dispersion == Decimal("6.66666667")


def test_amount_deviation_rule_and_neutral_cold_start() -> None:
    baseline = AmountBaseline(mean=Decimal("20"), dispersion=Decimal("5"), sample_count=3)
    context = AmountDeviationContextProvider({"customer-1": baseline}).get_context(
        transaction("txn-1", "50")
    )
    decision = assess(transaction("txn-1", "50"), context)
    neutral = assess(
        transaction("txn-1", "50"),
        RiskContext(
            amount_baseline=AmountBaseline(
                mean=Decimal("20"), dispersion=Decimal("0"), sample_count=3
            )
        ),
    )

    assert [reason.code for reason in decision.reasons] == ["AMOUNT_DEVIATION"]
    assert decision.engine_version == "rules-v1"
    assert neutral.reasons == ()


def test_insufficient_history_and_label_field_are_safe() -> None:
    baseline = AmountBaseline(mean=Decimal("20"), dispersion=Decimal("1"), sample_count=1)
    decision = assess(
        transaction("txn-1", "50"),
        AmountDeviationContextProvider({"customer-1": baseline}).get_context(
            transaction("txn-1", "50")
        ),
    )
    assert decision.reasons == ()

    with pytest.raises(ValidationError):
        RiskTransaction(
            transaction_id="txn-label",
            customer_id="customer-1",
            merchant_id="merchant-1",
            category="es_food",
            amount="10",
            source_step=1,
            source="api",
            event_time="2026-01-01T12:00:00Z",
            is_fraud=False,
        )
