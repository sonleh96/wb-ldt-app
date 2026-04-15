"""Deterministic analytics routines for scoring and prioritization."""

from src.schemas.domain import IndicatorGap, PrioritySignal


def compute_priority_signals(gaps: list[IndicatorGap], top_n: int = 3) -> list[PrioritySignal]:
    """Compute priority signals."""
    ranked = sorted(
        gaps,
        key=lambda gap: abs(gap.gap_percent) * gap.priority_weight,
        reverse=True,
    )

    signals: list[PrioritySignal] = []
    for gap in ranked[:top_n]:
        severity = abs(gap.gap_percent) * gap.priority_weight
        signals.append(
            PrioritySignal(
                indicator_id=gap.indicator_id,
                indicator_name=gap.indicator_name,
                severity=severity,
                reason=(
                    f"Gap {gap.gap_value:.2f} versus national benchmark "
                    f"({gap.gap_percent:.2%} relative gap)."
                ),
            )
        )
    return signals
