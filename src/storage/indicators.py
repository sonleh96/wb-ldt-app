"""Storage abstractions and indicator repository implementations."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Protocol

try:  # pragma: no cover - optional dependency path
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - optional dependency path
    psycopg = None  # type: ignore[assignment]


@dataclass(frozen=True)
class IndicatorObservation:
    """Class representing IndicatorObservation."""

    indicator_id: str
    indicator_name: str
    municipality_value: float
    national_value: float
    higher_is_better: bool
    priority_weight: float


class IndicatorRepository(Protocol):
    """Repository interface for indicator observations."""

    def list_for_context(self, municipality_id: str, category: str, year: int) -> list[IndicatorObservation]:
        """Return indicator observations for one municipality/category/year context."""


@dataclass(frozen=True)
class IndicatorTemplate:
    """Template describing one derived indicator and keyword family."""

    indicator_id: str
    indicator_name: str
    keywords: tuple[str, ...]
    higher_is_better: bool
    priority_weight: float


CATEGORY_INDICATORS: dict[str, tuple[IndicatorTemplate, ...]] = {
    "Environment": (
        IndicatorTemplate(
            indicator_id="air_quality_pressure",
            indicator_name="Air quality pressure signals",
            keywords=("air quality", "pm", "pollution", "emission", "smog"),
            higher_is_better=False,
            priority_weight=1.5,
        ),
        IndicatorTemplate(
            indicator_id="waste_service_gap",
            indicator_name="Waste service stress signals",
            keywords=("waste", "landfill", "collection", "recycling", "sanitation"),
            higher_is_better=False,
            priority_weight=1.3,
        ),
        IndicatorTemplate(
            indicator_id="environment_monitoring_coverage",
            indicator_name="Environment monitoring coverage",
            keywords=("monitoring", "sensor", "inspection", "measurement", "report"),
            higher_is_better=True,
            priority_weight=1.0,
        ),
    ),
    "Sustainable Transport": (
        IndicatorTemplate(
            indicator_id="transport_congestion_pressure",
            indicator_name="Transport congestion pressure",
            keywords=("congestion", "traffic", "delay", "bottleneck", "capacity"),
            higher_is_better=False,
            priority_weight=1.4,
        ),
        IndicatorTemplate(
            indicator_id="public_transport_coverage",
            indicator_name="Public transport coverage signals",
            keywords=("bus", "rail", "public transport", "mobility", "transit"),
            higher_is_better=True,
            priority_weight=1.2,
        ),
        IndicatorTemplate(
            indicator_id="transport_safety_pressure",
            indicator_name="Transport safety pressure",
            keywords=("safety", "accident", "crossing", "pedestrian", "injury"),
            higher_is_better=False,
            priority_weight=1.0,
        ),
    ),
}

GENERIC_INDICATORS: tuple[IndicatorTemplate, ...] = (
    IndicatorTemplate(
        indicator_id="policy_delivery_pressure",
        indicator_name="Policy delivery pressure",
        keywords=("implementation", "delivery", "constraint", "delay"),
        higher_is_better=False,
        priority_weight=1.2,
    ),
    IndicatorTemplate(
        indicator_id="investment_readiness",
        indicator_name="Public investment readiness",
        keywords=("ready", "pipeline", "investment", "project"),
        higher_is_better=True,
        priority_weight=1.1,
    ),
    IndicatorTemplate(
        indicator_id="institutional_capacity",
        indicator_name="Institutional capacity coverage",
        keywords=("capacity", "coordination", "governance", "monitoring"),
        higher_is_better=True,
        priority_weight=1.0,
    ),
)


class InMemoryIndicatorRepository:
    """In-memory implementation for IndicatorRepository."""

    def __init__(self) -> None:
        """Initialize the in-memory observation map."""

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
        """List observations for one context."""

        return list(self._by_key.get((municipality_id, category, year), []))


class PostgresIndicatorRepository:
    """Postgres-backed indicator repository derived from already-ingested chunks."""

    def __init__(self, *, database_url: str, max_chunk_samples: int = 4000) -> None:
        """Initialize the repository."""

        if psycopg is None:  # pragma: no cover - dependency guard
            raise ModuleNotFoundError("psycopg is required for PostgresIndicatorRepository")
        self._database_url = database_url
        self._max_chunk_samples = max(250, max_chunk_samples)

    @contextmanager
    def _connect(self) -> Iterator[object]:
        """Yield a PostgreSQL connection."""

        with psycopg.connect(self._database_url) as connection:  # type: ignore[union-attr]
            yield connection

    def list_for_context(self, municipality_id: str, category: str, year: int) -> list[IndicatorObservation]:
        """Return deterministic indicator observations derived from existing source chunks."""

        templates = CATEGORY_INDICATORS.get(category, GENERIC_INDICATORS)
        try:
            scoped_rows = self._load_scoped_rows(municipality_id=municipality_id, category=category)
            baseline_rows = self._load_baseline_rows(category=category)
        except Exception:
            return _fallback_observations(category=category)

        if not scoped_rows:
            return _fallback_observations(category=category)

        municipality_texts = [text for muni, text in scoped_rows if muni == municipality_id]
        if not municipality_texts:
            municipality_texts = [text for _, text in scoped_rows]

        national_texts = [text for _, text in baseline_rows]
        if not national_texts:
            national_texts = [text for muni, text in scoped_rows if muni != municipality_id]
        if not national_texts:
            national_texts = list(municipality_texts)

        observations: list[IndicatorObservation] = []
        for template in templates:
            municipality_rate = _keyword_match_rate(municipality_texts, template.keywords)
            national_rate = _keyword_match_rate(national_texts, template.keywords)
            observations.append(
                IndicatorObservation(
                    indicator_id=template.indicator_id,
                    indicator_name=template.indicator_name,
                    municipality_value=round(municipality_rate, 4),
                    national_value=round(national_rate, 4),
                    higher_is_better=template.higher_is_better,
                    priority_weight=template.priority_weight,
                )
            )
        return observations

    def _load_scoped_rows(self, *, municipality_id: str, category: str) -> list[tuple[str | None, str]]:
        """Load municipality-scoped and global chunk text rows for one category."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT municipality_id, text
                    FROM source_chunks
                    WHERE (category = %s OR category IS NULL)
                      AND (municipality_id = %s OR municipality_id IS NULL)
                    LIMIT %s
                    """,
                    (category, municipality_id, self._max_chunk_samples),
                )
                rows = cursor.fetchall()
        return [(str(muni) if muni is not None else None, str(text)) for muni, text in rows]

    def _load_baseline_rows(self, *, category: str) -> list[tuple[str | None, str]]:
        """Load global baseline chunk rows for one category."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT municipality_id, text
                    FROM source_chunks
                    WHERE (category = %s OR category IS NULL)
                      AND municipality_id IS NULL
                    LIMIT %s
                    """,
                    (category, self._max_chunk_samples),
                )
                rows = cursor.fetchall()
        return [(str(muni) if muni is not None else None, str(text)) for muni, text in rows]


def _keyword_match_rate(texts: list[str], keywords: tuple[str, ...]) -> float:
    """Return percentage of texts matching at least one keyword."""

    if not texts:
        return 0.0
    lowered_keywords = tuple(keyword.lower() for keyword in keywords)
    matches = 0
    for text in texts:
        lowered = text.lower()
        if any(keyword in lowered for keyword in lowered_keywords):
            matches += 1
    return (matches / max(1, len(texts))) * 100.0


def _fallback_observations(category: str) -> list[IndicatorObservation]:
    """Return deterministic fallback observations when SQL-derived metrics are unavailable."""

    templates = CATEGORY_INDICATORS.get(category, GENERIC_INDICATORS)
    observations: list[IndicatorObservation] = []
    for index, template in enumerate(templates):
        offset = index * 4.0
        if template.higher_is_better:
            municipality_value = 46.0 + offset
            national_value = 58.0 + offset
        else:
            municipality_value = 62.0 + offset
            national_value = 48.0 + offset
        observations.append(
            IndicatorObservation(
                indicator_id=template.indicator_id,
                indicator_name=template.indicator_name,
                municipality_value=municipality_value,
                national_value=national_value,
                higher_is_better=template.higher_is_better,
                priority_weight=template.priority_weight,
            )
        )
    return observations
