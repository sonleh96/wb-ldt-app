"""Deterministic analytics routines for scoring and prioritization."""

from dataclasses import dataclass
from math import isclose

from src.schemas.domain import IndicatorGap


@dataclass(frozen=True)
class GapInput:
    """Class representing GapInput."""
    indicator_id: str
    indicator_name: str
    municipality_value: float
    national_value: float
    higher_is_better: bool
    priority_weight: float = 1.0


def compute_indicator_gaps(observations: list[GapInput]) -> list[IndicatorGap]:
    """Compute indicator gaps."""
    gaps: list[IndicatorGap] = []
    for item in observations:
        if item.higher_is_better:
            gap_value = item.national_value - item.municipality_value
        else:
            gap_value = item.municipality_value - item.national_value

        if isclose(item.national_value, 0.0):
            gap_percent = 0.0
        else:
            gap_percent = gap_value / abs(item.national_value)

        gaps.append(
            IndicatorGap(
                indicator_id=item.indicator_id,
                indicator_name=item.indicator_name,
                municipality_value=item.municipality_value,
                national_value=item.national_value,
                gap_value=gap_value,
                gap_percent=gap_percent,
                higher_is_better=item.higher_is_better,
                priority_weight=item.priority_weight,
            )
        )
    return gaps
