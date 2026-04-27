"""Fake psycopg facade for Postgres-backed reference repository tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeReferenceDatabase:
    """Shared in-memory state for reference-repository fake SQL queries."""

    project_rows: dict[str, list[tuple[object, ...]]] = field(default_factory=dict)
    municipality_rows: dict[str, list[tuple[object, ...]]] = field(default_factory=dict)
    source_chunks: list[dict[str, object]] = field(default_factory=list)


class FakeReferenceCursor:
    """Minimal cursor implementation for reference repository SQL patterns."""

    def __init__(self, database: FakeReferenceDatabase) -> None:
        """Initialize the cursor."""

        self._database = database
        self._many: list[tuple[object, ...]] = []
        self._one: tuple[object, ...] | None = None

    def __enter__(self) -> FakeReferenceCursor:
        """Enter context manager."""

        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        """Exit context manager."""

        return False

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> None:
        """Execute one supported query pattern."""

        normalized = " ".join(query.split()).lower()
        params = params or tuple()
        self._many = []
        self._one = None

        if "from serbia_lsg_projects" in normalized and "select id" in normalized:
            self._many = list(self._database.project_rows.get("serbia_lsg_projects", []))
            return
        if "from serbia_wbif_projects" in normalized and "select id" in normalized:
            self._many = list(self._database.project_rows.get("serbia_wbif_projects", []))
            return
        if "from serbia_wbif_tas" in normalized and "select id" in normalized:
            self._many = list(self._database.project_rows.get("serbia_wbif_tas", []))
            return

        if "select distinct municipality_name, country_code" in normalized and "from serbia_municipal_development_plans" in normalized:
            self._many = list(self._database.municipality_rows.get("serbia_municipal_development_plans", []))
            return
        if "select distinct municipality_name, country_code" in normalized and "from serbia_lsg_projects" in normalized:
            self._many = list(self._database.municipality_rows.get("serbia_lsg_projects", []))
            return

        if "select distinct municipality_id from source_chunks" in normalized:
            ids = sorted(
                {
                    str(item["municipality_id"])
                    for item in self._database.source_chunks
                    if item.get("municipality_id")
                }
            )
            self._many = [(item,) for item in ids]
            return

        if "select municipality_id, text from source_chunks" in normalized:
            category = str(params[0]) if params else ""
            if "and (municipality_id = %s or municipality_id is null)" in normalized:
                municipality_id = str(params[1]) if len(params) > 1 else ""
                limit = int(params[2]) if len(params) > 2 else 1000
                rows = [
                    (
                        item.get("municipality_id"),
                        item.get("text"),
                    )
                    for item in self._database.source_chunks
                    if (item.get("category") in {category, None})
                    and (item.get("municipality_id") in {municipality_id, None})
                ]
                self._many = rows[:limit]
                return
            if "and municipality_id is null" in normalized:
                limit = int(params[1]) if len(params) > 1 else 1000
                rows = [
                    (
                        item.get("municipality_id"),
                        item.get("text"),
                    )
                    for item in self._database.source_chunks
                    if (item.get("category") in {category, None})
                    and item.get("municipality_id") is None
                ]
                self._many = rows[:limit]
                return

        raise AssertionError(f"Unsupported fake SQL: {query}")

    def fetchone(self) -> tuple[object, ...] | None:
        """Return one row."""

        return self._one

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return all rows."""

        return list(self._many)


class FakeReferenceConnection:
    """Minimal connection implementation for reference repository tests."""

    def __init__(self, database: FakeReferenceDatabase) -> None:
        """Initialize the connection."""

        self._database = database

    def __enter__(self) -> FakeReferenceConnection:
        """Enter context manager."""

        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        """Exit context manager."""

        return False

    def cursor(self) -> FakeReferenceCursor:
        """Return a new fake cursor."""

        return FakeReferenceCursor(self._database)

    def commit(self) -> None:
        """No-op commit."""

        return None


class FakeReferencePsycopg:
    """Minimal psycopg-compatible facade for reference repository tests."""

    def __init__(self, database: FakeReferenceDatabase | None = None) -> None:
        """Initialize the facade."""

        self.database = database or build_reference_database()

    def connect(self, _: str) -> FakeReferenceConnection:
        """Return a fake connection."""

        return FakeReferenceConnection(self.database)


def build_reference_database() -> FakeReferenceDatabase:
    """Build default staged data used by reference repository tests."""

    return FakeReferenceDatabase(
        project_rows={
            "serbia_lsg_projects": [
                (
                    "lsg-001",
                    "Uzice Air Monitoring Upgrade",
                    "Environment",
                    "Uzice",
                    "environment",
                    "LDT-UZI-001",
                    "City of Uzice",
                    {
                        "summary_text": "Municipal project to expand air and waste monitoring coverage.",
                        "attributes": {
                            "ga_signed": True,
                            "decision_signed": True,
                            "investment_amount_eur": 2000000,
                            "grant_agreement_value_eur": 1200000,
                            "cofinancing_amount_eur": 500000,
                            "project_sector_code": "E",
                        },
                    },
                ),
            ],
            "serbia_wbif_projects": [
                (
                    "wbif-001",
                    "Regional Waste Infrastructure Program",
                    "Environment",
                    None,
                    "environment",
                    "WBIF-ENV-1",
                    "Ministry of Environment",
                    {
                        "summary_text": "National-level waste and sanitation infrastructure support.",
                        "attributes": {
                            "status": "Ongoing",
                            "total_project_cost_eur": 3000000,
                            "grant_amount_eur": 700000,
                        },
                    },
                ),
            ],
            "serbia_wbif_tas": [
                (
                    "wbif-ta-001",
                    "Environment Technical Assistance",
                    "Environment",
                    None,
                    "environment",
                    "WBIF-TA-ENV-1",
                    "IFI TA Unit",
                    {
                        "summary_text": "TA support for implementation and readiness.",
                        "attributes": {"status": "Pipeline"},
                    },
                ),
            ],
        },
        municipality_rows={
            "serbia_municipal_development_plans": [("Uzice", "SRB"), ("Belgrade", "SRB")],
            "serbia_lsg_projects": [("Uzice", "SRB")],
        },
        source_chunks=[
            {
                "municipality_id": "srb-uzice",
                "category": "Environment",
                "text": "Air quality pollution reduction and waste management priorities for Uzice.",
            },
            {
                "municipality_id": "srb-uzice",
                "category": "Environment",
                "text": "Monitoring sensors and landfill remediation are listed as investments.",
            },
            {
                "municipality_id": None,
                "category": "Environment",
                "text": "National policy addresses emissions control and recycling infrastructure.",
            },
            {
                "municipality_id": None,
                "category": "Environment",
                "text": "National strategy highlights sanitation service coverage and reporting.",
            },
            {
                "municipality_id": "srb-novi-sad",
                "category": "Environment",
                "text": "Cross-municipality environmental dashboard and monitoring activities.",
            },
        ],
    )
