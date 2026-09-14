"""Deterministic, label-free customer amount baseline context."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_UP, Decimal

from fraudlatch.risk.models import AmountBaseline, RiskContext, RiskTransaction

BASELINE_QUANTUM = Decimal("0.00000001")


def build_amount_baselines(
    transactions: Iterable[RiskTransaction],
) -> dict[str, AmountBaseline]:
    """Build customer baselines from canonical fields only."""

    grouped: defaultdict[str, list[RiskTransaction]] = defaultdict(list)
    for transaction in transactions:
        grouped[transaction.customer_id].append(transaction)

    baselines: dict[str, AmountBaseline] = {}
    for customer_id, records in grouped.items():
        ordered = sorted(records, key=lambda item: (item.event_time, item.transaction_id))
        amounts = [record.amount for record in ordered]
        mean = sum(amounts, Decimal("0")) / len(amounts)
        dispersion = sum((abs(amount - mean) for amount in amounts), Decimal("0")) / len(amounts)
        baselines[customer_id] = AmountBaseline(
            mean=mean.quantize(BASELINE_QUANTUM, rounding=ROUND_HALF_UP),
            dispersion=dispersion.quantize(BASELINE_QUANTUM, rounding=ROUND_HALF_UP),
            sample_count=len(amounts),
        )
    return baselines


class AmountDeviationContextProvider:
    """Look up a prebuilt customer baseline without calculating a score."""

    def __init__(self, baselines: Mapping[str, AmountBaseline]) -> None:
        self.baselines = dict(baselines)

    def get_context(self, transaction: RiskTransaction) -> RiskContext:
        """Return a baseline context or deterministic neutral cold-start context."""

        return RiskContext(amount_baseline=self.baselines.get(transaction.customer_id))
