"""Tests for Postgres-backed municipality/project/indicator repositories."""

from src.storage.indicators import PostgresIndicatorRepository
from src.storage.municipalities import PostgresMunicipalityRepository
from src.storage.projects import PostgresProjectRepository
from tests.unit.fake_reference_psycopg import FakeReferencePsycopg, build_reference_database


def test_postgres_project_repository_maps_staged_rows_to_ranking_records(monkeypatch) -> None:
    """Project repository should return ranking-compatible rows from staged tables."""

    fake_psycopg = FakeReferencePsycopg(build_reference_database())
    monkeypatch.setattr("src.storage.projects.psycopg", fake_psycopg)

    repository = PostgresProjectRepository(database_url="postgresql://fake")
    projects = repository.list_by_category("Environment")

    assert {item.project_id for item in projects} >= {"lsg-001", "wbif-001", "wbif-ta-001"}
    uzice_project = next(item for item in projects if item.project_id == "lsg-001")
    assert uzice_project.municipality_id == "srb-uzice"
    assert uzice_project.status == "ready"
    assert float(uzice_project.metadata["development_plan_alignment"]) > 0.75
    assert uzice_project.metadata["indicator_keywords"]


def test_postgres_municipality_repository_reads_staged_and_chunk_backed_ids(monkeypatch) -> None:
    """Municipality repository should resolve both named and chunk-only municipalities."""

    fake_psycopg = FakeReferencePsycopg(build_reference_database())
    monkeypatch.setattr("src.storage.municipalities.psycopg", fake_psycopg)

    repository = PostgresMunicipalityRepository(database_url="postgresql://fake")
    uzice = repository.get_by_id("srb-uzice")
    novi_sad = repository.get_by_id("srb-novi-sad")

    assert uzice is not None
    assert uzice.municipality_name == "Uzice"
    assert novi_sad is not None
    assert novi_sad.municipality_name == "Novi Sad"


def test_postgres_indicator_repository_derives_observations_from_existing_chunks(monkeypatch) -> None:
    """Indicator repository should derive deterministic observations from chunk corpus text."""

    fake_psycopg = FakeReferencePsycopg(build_reference_database())
    monkeypatch.setattr("src.storage.indicators.psycopg", fake_psycopg)

    repository = PostgresIndicatorRepository(database_url="postgresql://fake")
    observations = repository.list_for_context(
        municipality_id="srb-uzice",
        category="Environment",
        year=2024,
    )

    assert len(observations) >= 3
    indicator_ids = {item.indicator_id for item in observations}
    assert "air_quality_pressure" in indicator_ids
    assert all(item.priority_weight > 0 for item in observations)
    assert any(item.municipality_value > 0 for item in observations)
    assert any(item.national_value > 0 for item in observations)
