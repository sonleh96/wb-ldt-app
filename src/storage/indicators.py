"""Storage abstractions and in-memory repository implementations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class IndicatorObservation:
    """Class representing IndicatorObservation."""
    indicator_id: str
    indicator_name: str
    municipality_value: float
    national_value: float
    higher_is_better: bool
    priority_weight: float


class InMemoryIndicatorRepository:
    """In-memory implementation for IndicatorRepository."""
    def __init__(self) -> None:
        """Initialize the instance and its dependencies."""
        self._by_key: dict[tuple[str, str, int], list[IndicatorObservation]] = {
            (
                "srb-belgrade",
                "Environment",
                2024,
            ): [
                IndicatorObservation(
                    indicator_id="pm25",
                    indicator_name="PM 2.5 concentration",
                    municipality_value=18.0,
                    national_value=14.0,
                    higher_is_better=False,
                    priority_weight=1.5,
                ),
                IndicatorObservation(
                    indicator_id="waste_access",
                    indicator_name="Population without access to waste disposal",
                    municipality_value=7.0,
                    national_value=5.0,
                    higher_is_better=False,
                    priority_weight=1.2,
                ),
                IndicatorObservation(
                    indicator_id="waste_points",
                    indicator_name="Waste disposal points per 10000",
                    municipality_value=9.5,
                    national_value=10.0,
                    higher_is_better=True,
                    priority_weight=1.0,
                ),
            ]
        }

    def list_for_context(self, municipality_id: str, category: str, year: int) -> list[IndicatorObservation]:
        """List for context."""
        return list(self._by_key.get((municipality_id, category, year), []))
