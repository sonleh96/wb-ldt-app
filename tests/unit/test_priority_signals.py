from src.schemas.domain import IndicatorGap
from src.analytics.priority_signals import compute_priority_signals


def test_priority_signals_sort_by_weighted_severity() -> None:
    gaps = [
        IndicatorGap(
            indicator_id="a",
            indicator_name="A",
            municipality_value=5,
            national_value=10,
            gap_value=5,
            gap_percent=0.5,
            higher_is_better=True,
            priority_weight=1.0,
        ),
        IndicatorGap(
            indicator_id="b",
            indicator_name="B",
            municipality_value=2,
            national_value=10,
            gap_value=8,
            gap_percent=0.8,
            higher_is_better=True,
            priority_weight=0.5,
        ),
    ]
    signals = compute_priority_signals(gaps, top_n=1)

    assert len(signals) == 1
    assert signals[0].indicator_id == "a"
