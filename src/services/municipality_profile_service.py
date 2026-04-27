"""Service-layer orchestration and business logic."""

from src.analytics.gap_analysis import GapInput, compute_indicator_gaps
from src.analytics.priority_signals import compute_priority_signals
from src.core.errors import AppError
from src.schemas.domain import MunicipalityProfile, PrioritySignal
from src.storage.indicators import IndicatorRepository
from src.storage.municipalities import MunicipalityRepository


class MunicipalityProfileService:
    """Service for MunicipalityProfile workflows and operations."""
    def __init__(
        self,
        *,
        municipality_repository: MunicipalityRepository,
        indicator_repository: IndicatorRepository,
    ) -> None:
        """Initialize the instance and its dependencies."""
        self._municipality_repository = municipality_repository
        self._indicator_repository = indicator_repository

    def build_profile(self, municipality_id: str, category: str, year: int) -> MunicipalityProfile:
        """Build profile."""
        municipality = self._municipality_repository.get_by_id(municipality_id)
        if not municipality:
            raise AppError(
                status_code=404,
                code="municipality_not_found",
                message=f"Municipality {municipality_id} was not found.",
                target="municipality_id",
            )

        observations = self._indicator_repository.list_for_context(municipality_id, category, year)
        if not observations:
            raise AppError(
                status_code=404,
                code="indicators_not_found",
                message=(
                    f"No indicator observations found for municipality={municipality_id}, "
                    f"category={category}, year={year}."
                ),
            )

        gaps = compute_indicator_gaps(
            [
                GapInput(
                    indicator_id=item.indicator_id,
                    indicator_name=item.indicator_name,
                    municipality_value=item.municipality_value,
                    national_value=item.national_value,
                    higher_is_better=item.higher_is_better,
                    priority_weight=item.priority_weight,
                )
                for item in observations
            ]
        )

        return MunicipalityProfile(
            municipality_id=municipality.municipality_id,
            municipality_name=municipality.municipality_name,
            country_code=municipality.country_code,
            category=category,
            year=year,
            indicator_values={item.indicator_id: item.municipality_value for item in observations},
            national_averages={item.indicator_id: item.national_value for item in observations},
            indicator_gaps=gaps,
        )

    def compute_priority_signals(
        self,
        municipality_id: str,
        category: str,
        year: int,
        top_n: int = 3,
    ) -> list[PrioritySignal]:
        """Compute priority signals."""
        profile = self.build_profile(municipality_id, category, year)
        return compute_priority_signals(profile.indicator_gaps, top_n=top_n)
