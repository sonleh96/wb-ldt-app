from src.services.municipality_profile_service import MunicipalityProfileService
from src.storage.indicators import InMemoryIndicatorRepository
from src.storage.municipalities import InMemoryMunicipalityRepository


def test_municipality_profile_service_builds_profile_with_gaps() -> None:
    service = MunicipalityProfileService(
        municipality_repository=InMemoryMunicipalityRepository(),
        indicator_repository=InMemoryIndicatorRepository(),
    )

    profile = service.build_profile("srb-belgrade", "Environment", 2024)
    assert profile.municipality_name == "Belgrade"
    assert len(profile.indicator_gaps) > 0


def test_municipality_profile_service_priority_signals() -> None:
    service = MunicipalityProfileService(
        municipality_repository=InMemoryMunicipalityRepository(),
        indicator_repository=InMemoryIndicatorRepository(),
    )

    signals = service.compute_priority_signals("srb-belgrade", "Environment", 2024, top_n=2)
    assert len(signals) == 2
