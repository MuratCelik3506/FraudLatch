"""Pure rules-v1 risk evaluation."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from fraudlatch.risk.config import RulesConfig
from fraudlatch.risk.models import RiskContext, RiskDecision, RiskLevel, RiskReason, RiskTransaction

SCORE_QUANTUM = Decimal("0.0001")


def assess(
    transaction: RiskTransaction,
    context: RiskContext | None = None,
    config: RulesConfig | None = None,
) -> RiskDecision:
    """Return a deterministic decision from transaction and optional context."""

    active_context = context or RiskContext()
    rules = config or RulesConfig()
    reasons: list[RiskReason] = []
    amount_threshold = rules.category_amount_thresholds.get(
        transaction.category, rules.global_amount_threshold
    )

    if transaction.amount >= amount_threshold:
        reasons.append(RiskReason(code="HIGH_AMOUNT", contribution=rules.high_amount_weight))
    if active_context.customer_velocity >= rules.customer_velocity_threshold:
        reasons.append(
            RiskReason(code="CUSTOMER_VELOCITY", contribution=rules.customer_velocity_weight)
        )
    if active_context.merchant_velocity >= rules.merchant_velocity_threshold:
        reasons.append(
            RiskReason(code="MERCHANT_VELOCITY", contribution=rules.merchant_velocity_weight)
        )
    category_weight = rules.category_risk_weights.get(transaction.category, Decimal("0"))
    if category_weight > 0:
        reasons.append(RiskReason(code="CATEGORY_RISK", contribution=category_weight))

    score = min(sum((reason.contribution for reason in reasons), Decimal("0")), Decimal("1"))
    score = score.quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)
    level: RiskLevel = (
        "HIGH" if score >= Decimal("0.70") else "MEDIUM" if score >= Decimal("0.40") else "LOW"
    )
    return RiskDecision(
        risk_score=score,
        risk_level=level,
        reasons=tuple(reasons),
    )
