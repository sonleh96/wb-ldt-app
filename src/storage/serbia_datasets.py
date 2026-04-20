"""Storage backends for canonical Serbia dataset SQL rows."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Iterator, Protocol

from src.schemas.serbia_dataset import (
    SerbiaDatasetFamily,
    SerbiaDatasetIngestionReadiness,
    SerbiaDatasetMirrorStatus,
    SerbiaDatasetRow,
    utcnow,
)

try:  # pragma: no cover - optional dependency path
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - optional dependency path
    psycopg = None  # type: ignore[assignment]


SERBIA_DATASET_TABLES: dict[SerbiaDatasetFamily, str] = {
    "serbia_national_documents": "serbia_national_documents",
    "serbia_municipal_development_plans": "serbia_municipal_development_plans",
    "serbia_lsg_projects": "serbia_lsg_projects",
    "serbia_wbif_projects": "serbia_wbif_projects",
    "serbia_wbif_tas": "serbia_wbif_tas",
}


class SerbiaDatasetRepository(Protocol):
    """Repository interface for Serbia dataset staging rows."""

    def upsert_row(self, row: SerbiaDatasetRow) -> SerbiaDatasetRow:
        """Insert or update one row by stable id."""

    def get_row(self, *, dataset_family: SerbiaDatasetFamily, row_id: str) -> SerbiaDatasetRow | None:
        """Return one row by family and id."""

    def list_rows(
        self,
        *,
        dataset_families: set[SerbiaDatasetFamily] | None = None,
        ingestion_readinesses: set[SerbiaDatasetIngestionReadiness] | None = None,
        mirror_statuses: set[SerbiaDatasetMirrorStatus] | None = None,
        has_source_id: bool | None = None,
        require_gcs_uri: bool | None = None,
        limit: int | None = None,
    ) -> list[SerbiaDatasetRow]:
        """Return rows filtered by lifecycle state."""


class InMemorySerbiaDatasetRepository:
    """In-memory implementation for Serbia dataset staging rows."""

    def __init__(self) -> None:
        """Initialize in-memory row storage."""

        self._rows: dict[SerbiaDatasetFamily, dict[str, SerbiaDatasetRow]] = {
            family: {} for family in SERBIA_DATASET_TABLES
        }

    def upsert_row(self, row: SerbiaDatasetRow) -> SerbiaDatasetRow:
        """Insert or update one row by stable id."""

        previous = self._rows[row.dataset_family].get(row.id)
        created_at = previous.created_at if previous else row.created_at
        updated = row.model_copy(update={"created_at": created_at, "updated_at": utcnow()})
        self._rows[row.dataset_family][row.id] = updated
        return updated

    def get_row(self, *, dataset_family: SerbiaDatasetFamily, row_id: str) -> SerbiaDatasetRow | None:
        """Return one row by family and id."""

        return self._rows[dataset_family].get(row_id)

    def list_rows(
        self,
        *,
        dataset_families: set[SerbiaDatasetFamily] | None = None,
        ingestion_readinesses: set[SerbiaDatasetIngestionReadiness] | None = None,
        mirror_statuses: set[SerbiaDatasetMirrorStatus] | None = None,
        has_source_id: bool | None = None,
        require_gcs_uri: bool | None = None,
        limit: int | None = None,
    ) -> list[SerbiaDatasetRow]:
        """Return rows filtered by lifecycle state."""

        families = dataset_families or set(SERBIA_DATASET_TABLES.keys())
        rows: list[SerbiaDatasetRow] = []
        for family in families:
            rows.extend(self._rows[family].values())

        filtered: list[SerbiaDatasetRow] = []
        for row in rows:
            if ingestion_readinesses and row.ingestion_readiness not in ingestion_readinesses:
                continue
            if mirror_statuses and row.mirror_status not in mirror_statuses:
                continue
            if has_source_id is True and not row.source_id:
                continue
            if has_source_id is False and row.source_id:
                continue
            if require_gcs_uri is True and not row.gcs_uri:
                continue
            if require_gcs_uri is False and row.gcs_uri:
                continue
            filtered.append(row)

        filtered.sort(key=lambda item: item.updated_at, reverse=True)
        if limit is not None:
            return filtered[:limit]
        return filtered


class PostgresSerbiaDatasetRepository:
    """PostgreSQL/Supabase-backed repository for Serbia dataset rows."""

    def __init__(self, *, database_url: str) -> None:
        """Initialize the repository and ensure tables exist."""

        if psycopg is None:  # pragma: no cover - dependency guard
            raise ModuleNotFoundError("psycopg is required for PostgresSerbiaDatasetRepository")
        self._database_url = database_url
        self._ensure_schema()

    @contextmanager
    def _connect(self) -> Iterator[object]:
        """Yield a database connection."""

        with psycopg.connect(self._database_url) as connection:  # type: ignore[union-attr]
            yield connection

    def _ensure_schema(self) -> None:
        """Create Serbia dataset tables when absent."""

        for table_name in SERBIA_DATASET_TABLES.values():
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {table_name} (
                            id TEXT PRIMARY KEY,
                            dataset_name TEXT NOT NULL,
                            source_file_name TEXT NOT NULL,
                            source_row_number INTEGER NOT NULL,
                            title TEXT NOT NULL,
                            country_code TEXT NOT NULL DEFAULT 'SRB',
                            country_name TEXT NOT NULL DEFAULT 'Serbia',
                            municipality_name TEXT NULL,
                            municipality_code TEXT NULL,
                            district_name TEXT NULL,
                            region_name TEXT NULL,
                            beneficiary_country TEXT NULL,
                            beneficiary_body TEXT NULL,
                            project_code TEXT NULL,
                            sector TEXT NULL,
                            category TEXT NULL,
                            year_value INTEGER NULL,
                            source_url TEXT NULL,
                            resolved_document_url TEXT NULL,
                            landing_page_url TEXT NULL,
                            url_kind TEXT NOT NULL CHECK (
                                url_kind IN ('direct_document', 'landing_page', 'cloud_drive', 'office_doc', 'archive', 'unknown')
                            ),
                            ingestion_readiness TEXT NOT NULL CHECK (
                                ingestion_readiness IN ('ready', 'needs_resolver', 'metadata_only', 'missing_url')
                            ),
                            mirror_status TEXT NOT NULL CHECK (
                                mirror_status IN ('not_started', 'skipped', 'mirrored', 'failed')
                            ) DEFAULT 'not_started',
                            mirror_error TEXT NULL,
                            gcs_uri TEXT NULL,
                            source_id TEXT NULL,
                            document_checksum_sha256 TEXT NULL,
                            document_size_bytes BIGINT NULL,
                            document_mime_type TEXT NULL,
                            raw_payload JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                    cursor.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_{table_name}_mirror
                        ON {table_name} (ingestion_readiness, mirror_status, source_id)
                        """
                    )
                    cursor.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_{table_name}_updated
                        ON {table_name} (updated_at DESC)
                        """
                    )
                connection.commit()

    def upsert_row(self, row: SerbiaDatasetRow) -> SerbiaDatasetRow:
        """Insert or update one row by stable id."""

        table_name = SERBIA_DATASET_TABLES[row.dataset_family]
        payload = row.model_dump(mode="json")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {table_name} (
                        id,
                        dataset_name,
                        source_file_name,
                        source_row_number,
                        title,
                        country_code,
                        country_name,
                        municipality_name,
                        municipality_code,
                        district_name,
                        region_name,
                        beneficiary_country,
                        beneficiary_body,
                        project_code,
                        sector,
                        category,
                        year_value,
                        source_url,
                        resolved_document_url,
                        landing_page_url,
                        url_kind,
                        ingestion_readiness,
                        mirror_status,
                        mirror_error,
                        gcs_uri,
                        source_id,
                        document_checksum_sha256,
                        document_size_bytes,
                        document_mime_type,
                        raw_payload,
                        created_at,
                        updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        dataset_name = EXCLUDED.dataset_name,
                        source_file_name = EXCLUDED.source_file_name,
                        source_row_number = EXCLUDED.source_row_number,
                        title = EXCLUDED.title,
                        country_code = EXCLUDED.country_code,
                        country_name = EXCLUDED.country_name,
                        municipality_name = EXCLUDED.municipality_name,
                        municipality_code = EXCLUDED.municipality_code,
                        district_name = EXCLUDED.district_name,
                        region_name = EXCLUDED.region_name,
                        beneficiary_country = EXCLUDED.beneficiary_country,
                        beneficiary_body = EXCLUDED.beneficiary_body,
                        project_code = EXCLUDED.project_code,
                        sector = EXCLUDED.sector,
                        category = EXCLUDED.category,
                        year_value = EXCLUDED.year_value,
                        source_url = EXCLUDED.source_url,
                        resolved_document_url = EXCLUDED.resolved_document_url,
                        landing_page_url = EXCLUDED.landing_page_url,
                        url_kind = EXCLUDED.url_kind,
                        ingestion_readiness = EXCLUDED.ingestion_readiness,
                        mirror_status = EXCLUDED.mirror_status,
                        mirror_error = EXCLUDED.mirror_error,
                        gcs_uri = EXCLUDED.gcs_uri,
                        source_id = EXCLUDED.source_id,
                        document_checksum_sha256 = EXCLUDED.document_checksum_sha256,
                        document_size_bytes = EXCLUDED.document_size_bytes,
                        document_mime_type = EXCLUDED.document_mime_type,
                        raw_payload = EXCLUDED.raw_payload,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        payload["id"],
                        payload["dataset_name"],
                        payload["source_file_name"],
                        payload["source_row_number"],
                        payload["title"],
                        payload["country_code"],
                        payload["country_name"],
                        payload["municipality_name"],
                        payload["municipality_code"],
                        payload["district_name"],
                        payload["region_name"],
                        payload["beneficiary_country"],
                        payload["beneficiary_body"],
                        payload["project_code"],
                        payload["sector"],
                        payload["category"],
                        payload["year_value"],
                        payload["source_url"],
                        payload["resolved_document_url"],
                        payload["landing_page_url"],
                        payload["url_kind"],
                        payload["ingestion_readiness"],
                        payload["mirror_status"],
                        payload["mirror_error"],
                        payload["gcs_uri"],
                        payload["source_id"],
                        payload["document_checksum_sha256"],
                        payload["document_size_bytes"],
                        payload["document_mime_type"],
                        json.dumps(payload["raw_payload"]),
                        payload["created_at"],
                        payload["updated_at"],
                    ),
                )
            connection.commit()
        stored = self.get_row(dataset_family=row.dataset_family, row_id=row.id)
        if stored is None:  # pragma: no cover - defensive guard
            raise RuntimeError(f"Failed to upsert Serbia dataset row {row.dataset_family}:{row.id}")
        return stored

    def get_row(self, *, dataset_family: SerbiaDatasetFamily, row_id: str) -> SerbiaDatasetRow | None:
        """Return one row by family and id."""

        table_name = SERBIA_DATASET_TABLES[dataset_family]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM {table_name} WHERE id = %s",
                    (row_id,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return self._row_from_tuple(dataset_family=dataset_family, row=row)

    def list_rows(
        self,
        *,
        dataset_families: set[SerbiaDatasetFamily] | None = None,
        ingestion_readinesses: set[SerbiaDatasetIngestionReadiness] | None = None,
        mirror_statuses: set[SerbiaDatasetMirrorStatus] | None = None,
        has_source_id: bool | None = None,
        require_gcs_uri: bool | None = None,
        limit: int | None = None,
    ) -> list[SerbiaDatasetRow]:
        """Return rows filtered by lifecycle state."""

        families = dataset_families or set(SERBIA_DATASET_TABLES.keys())
        rows: list[SerbiaDatasetRow] = []
        for family in families:
            rows.extend(
                self._list_rows_for_family(
                    dataset_family=family,
                    ingestion_readinesses=ingestion_readinesses,
                    mirror_statuses=mirror_statuses,
                    has_source_id=has_source_id,
                    require_gcs_uri=require_gcs_uri,
                )
            )
        rows.sort(key=lambda item: item.updated_at, reverse=True)
        if limit is not None:
            return rows[:limit]
        return rows

    def _list_rows_for_family(
        self,
        *,
        dataset_family: SerbiaDatasetFamily,
        ingestion_readinesses: set[SerbiaDatasetIngestionReadiness] | None,
        mirror_statuses: set[SerbiaDatasetMirrorStatus] | None,
        has_source_id: bool | None,
        require_gcs_uri: bool | None,
    ) -> list[SerbiaDatasetRow]:
        """Return filtered rows for one family table."""

        table_name = SERBIA_DATASET_TABLES[dataset_family]
        clauses = ["1=1"]
        params: list[object] = []
        if ingestion_readinesses:
            clauses.append("ingestion_readiness = ANY(%s)")
            params.append(list(ingestion_readinesses))
        if mirror_statuses:
            clauses.append("mirror_status = ANY(%s)")
            params.append(list(mirror_statuses))
        if has_source_id is True:
            clauses.append("source_id IS NOT NULL")
        if has_source_id is False:
            clauses.append("source_id IS NULL")
        if require_gcs_uri is True:
            clauses.append("gcs_uri IS NOT NULL")
        if require_gcs_uri is False:
            clauses.append("gcs_uri IS NULL")

        query = f"SELECT * FROM {table_name} WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                db_rows = cursor.fetchall()
        return [self._row_from_tuple(dataset_family=dataset_family, row=item) for item in db_rows]

    @staticmethod
    def _row_from_tuple(*, dataset_family: SerbiaDatasetFamily, row: tuple[object, ...]) -> SerbiaDatasetRow:
        """Convert one SQL row tuple into a typed dataset row."""

        (
            row_id,
            dataset_name,
            source_file_name,
            source_row_number,
            title,
            country_code,
            country_name,
            municipality_name,
            municipality_code,
            district_name,
            region_name,
            beneficiary_country,
            beneficiary_body,
            project_code,
            sector,
            category,
            year_value,
            source_url,
            resolved_document_url,
            landing_page_url,
            url_kind,
            ingestion_readiness,
            mirror_status,
            mirror_error,
            gcs_uri,
            source_id,
            document_checksum_sha256,
            document_size_bytes,
            document_mime_type,
            raw_payload,
            created_at,
            updated_at,
        ) = row
        payload = raw_payload if isinstance(raw_payload, dict) else json.loads(str(raw_payload))
        return SerbiaDatasetRow(
            id=str(row_id),
            dataset_family=dataset_family,
            dataset_name=str(dataset_name),
            source_file_name=str(source_file_name),
            source_row_number=int(source_row_number),
            title=str(title),
            country_code=str(country_code),
            country_name=str(country_name),
            municipality_name=str(municipality_name) if municipality_name is not None else None,
            municipality_code=str(municipality_code) if municipality_code is not None else None,
            district_name=str(district_name) if district_name is not None else None,
            region_name=str(region_name) if region_name is not None else None,
            beneficiary_country=str(beneficiary_country) if beneficiary_country is not None else None,
            beneficiary_body=str(beneficiary_body) if beneficiary_body is not None else None,
            project_code=str(project_code) if project_code is not None else None,
            sector=str(sector) if sector is not None else None,
            category=str(category) if category is not None else None,
            year_value=int(year_value) if year_value is not None else None,
            source_url=str(source_url) if source_url is not None else None,
            resolved_document_url=str(resolved_document_url) if resolved_document_url is not None else None,
            landing_page_url=str(landing_page_url) if landing_page_url is not None else None,
            url_kind=str(url_kind),  # type: ignore[arg-type]
            ingestion_readiness=str(ingestion_readiness),  # type: ignore[arg-type]
            mirror_status=str(mirror_status),  # type: ignore[arg-type]
            mirror_error=str(mirror_error) if mirror_error is not None else None,
            gcs_uri=str(gcs_uri) if gcs_uri is not None else None,
            source_id=str(source_id) if source_id is not None else None,
            document_checksum_sha256=(
                str(document_checksum_sha256) if document_checksum_sha256 is not None else None
            ),
            document_size_bytes=int(document_size_bytes) if document_size_bytes is not None else None,
            document_mime_type=str(document_mime_type) if document_mime_type is not None else None,
            raw_payload=payload,
            created_at=created_at,  # type: ignore[arg-type]
            updated_at=updated_at,  # type: ignore[arg-type]
        )
