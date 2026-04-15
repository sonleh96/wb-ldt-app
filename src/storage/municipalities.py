"""Storage abstractions and in-memory repository implementations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MunicipalityRecord:
    """Typed schema for MunicipalityRecord."""
    municipality_id: str
    municipality_name: str
    country_code: str


class InMemoryMunicipalityRepository:
    """In-memory implementation for MunicipalityRepository."""
    def __init__(self) -> None:
        """Initialize the instance and its dependencies."""
        self._records = {
            "srb-belgrade": MunicipalityRecord(
                municipality_id="srb-belgrade",
                municipality_name="Belgrade",
                country_code="SRB",
            ),
            "srb-nis": MunicipalityRecord(
                municipality_id="srb-nis",
                municipality_name="Nis",
                country_code="SRB",
            ),
        }

    def get_by_id(self, municipality_id: str) -> MunicipalityRecord | None:
        """Return by id."""
        return self._records.get(municipality_id)
