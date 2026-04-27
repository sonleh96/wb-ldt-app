"""Storage abstractions and municipality repository implementations."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Protocol

from src.ingestion.serbia_operational import canonical_serbia_municipality_id

try:  # pragma: no cover - optional dependency path
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - optional dependency path
    psycopg = None  # type: ignore[assignment]


@dataclass(frozen=True)
class MunicipalityRecord:
    """Typed schema for MunicipalityRecord."""

    municipality_id: str
    municipality_name: str
    country_code: str


class MunicipalityRepository(Protocol):
    """Repository interface for municipality reference records."""

    def get_by_id(self, municipality_id: str) -> MunicipalityRecord | None:
        """Return one municipality record by canonical id."""


class InMemoryMunicipalityRepository:
    """In-memory implementation for MunicipalityRepository."""

    def __init__(self) -> None:
        """Initialize the in-memory municipality records."""

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
        """Return one municipality by id."""

        return self._records.get(municipality_id)


class PostgresMunicipalityRepository:
    """Postgres-backed municipality repository using staged Serbia datasets."""

    def __init__(self, *, database_url: str) -> None:
        """Initialize the repository."""

        if psycopg is None:  # pragma: no cover - dependency guard
            raise ModuleNotFoundError("psycopg is required for PostgresMunicipalityRepository")
        self._database_url = database_url

    @contextmanager
    def _connect(self) -> Iterator[object]:
        """Yield a PostgreSQL connection."""

        with psycopg.connect(self._database_url) as connection:  # type: ignore[union-attr]
            yield connection

    def get_by_id(self, municipality_id: str) -> MunicipalityRecord | None:
        """Return one municipality by canonical id."""

        records = self._load_records()
        record = records.get(municipality_id)
        if record is not None:
            return record
        if municipality_id.startswith("srb-"):
            fallback_name = municipality_id.replace("srb-", "").replace("-", " ").title()
            return MunicipalityRecord(
                municipality_id=municipality_id,
                municipality_name=fallback_name,
                country_code="SRB",
            )
        return None

    def _load_records(self) -> dict[str, MunicipalityRecord]:
        """Load municipality records from staged tables and source chunks."""

        records: dict[str, MunicipalityRecord] = {}
        for municipality_name, country_code in self._load_named_municipalities():
            canonical_id = canonical_serbia_municipality_id(municipality_name)
            if not canonical_id:
                continue
            records[canonical_id] = MunicipalityRecord(
                municipality_id=canonical_id,
                municipality_name=municipality_name,
                country_code=country_code or "SRB",
            )
        for canonical_id in self._load_chunk_municipality_ids():
            if canonical_id not in records:
                records[canonical_id] = MunicipalityRecord(
                    municipality_id=canonical_id,
                    municipality_name=canonical_id.replace("srb-", "").replace("-", " ").title(),
                    country_code="SRB",
                )
        return records

    def _load_named_municipalities(self) -> list[tuple[str, str]]:
        """Load municipality names from staged municipal and local-project tables."""

        rows: list[tuple[str, str]] = []
        for table_name in ("serbia_municipal_development_plans", "serbia_lsg_projects"):
            try:
                with self._connect() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f"""
                            SELECT DISTINCT municipality_name, country_code
                            FROM {table_name}
                            WHERE municipality_name IS NOT NULL AND municipality_name <> ''
                            """
                        )
                        rows.extend((str(name), str(country)) for name, country in cursor.fetchall())
            except Exception:
                continue
        return rows

    def _load_chunk_municipality_ids(self) -> list[str]:
        """Load canonical municipality ids observed in retrieval chunks."""

        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT DISTINCT municipality_id
                        FROM source_chunks
                        WHERE municipality_id IS NOT NULL AND municipality_id <> ''
                        """
                    )
                    return [str(row[0]) for row in cursor.fetchall()]
        except Exception:
            return []
