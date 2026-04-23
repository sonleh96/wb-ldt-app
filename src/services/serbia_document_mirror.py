"""Resolve and mirror Serbia dataset document URLs into Google Cloud Storage."""

from __future__ import annotations

import hashlib
import mimetypes
import re
from dataclasses import dataclass
from html import unescape
from typing import Protocol
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen

from src.schemas.serbia_dataset import (
    SerbiaDatasetFamily,
    SerbiaDatasetMirrorStatus,
    SerbiaDatasetRow,
    SerbiaDocumentMirrorRowResult,
    SerbiaDocumentMirrorSummary,
    SerbiaIngestionJobRefreshMode,
)
from src.storage.serbia_datasets import SerbiaDatasetRepository

try:  # pragma: no cover - optional dependency path
    from google.cloud import storage as gcs_storage
except ModuleNotFoundError:  # pragma: no cover - optional dependency path
    gcs_storage = None  # type: ignore[assignment]


NATIONAL_DATASET_FAMILY: SerbiaDatasetFamily = "serbia_national_documents"
NATIONAL_BATCH_RESERVE_RATIO = 0.25


@dataclass
class FetchedDocument:
    """Fetched remote document payload."""

    content: bytes
    final_url: str
    mime_type: str | None = None
    content_disposition: str | None = None


class RemoteDocumentFetcher(Protocol):
    """Protocol for fetching remote binary and text payloads."""

    def fetch_document(self, url: str, *, timeout_seconds: int, max_retries: int) -> FetchedDocument:
        """Return remote content and metadata."""

    def fetch_text(self, url: str, *, timeout_seconds: int, max_retries: int) -> str:
        """Return remote HTML/text body."""


class MirrorObjectStore(Protocol):
    """Protocol for uploading mirrored document bytes."""

    def upload_bytes(self, *, object_name: str, content: bytes, content_type: str | None) -> str:
        """Upload bytes and return the resulting gs:// URI."""


class UrllibRemoteDocumentFetcher:
    """HTTP fetcher implementation using urllib from the standard library."""

    def fetch_document(self, url: str, *, timeout_seconds: int, max_retries: int) -> FetchedDocument:
        """Return remote document bytes and response metadata."""

        last_error: Exception | None = None
        for _ in range(max(1, max_retries + 1)):
            try:
                request = Request(url, headers={"User-Agent": "ldt-de-v2/serbia-mirror"})
                with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
                    content = response.read()
                    final_url = str(response.geturl())
                    mime_type = response.headers.get("Content-Type")
                    content_disposition = response.headers.get("Content-Disposition")
                    return FetchedDocument(
                        content=content,
                        final_url=final_url,
                        mime_type=mime_type,
                        content_disposition=content_disposition,
                    )
            except Exception as exc:  # pragma: no cover - network error path
                last_error = exc
        raise RuntimeError(f"Failed to fetch document URL: {url}. Error: {last_error}")

    def fetch_text(self, url: str, *, timeout_seconds: int, max_retries: int) -> str:
        """Return decoded text from a remote URL."""

        fetched = self.fetch_document(url, timeout_seconds=timeout_seconds, max_retries=max_retries)
        for encoding in ("utf-8", "latin-1"):
            try:
                return fetched.content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return fetched.content.decode("utf-8", errors="ignore")


class GCSMirrorObjectStore:
    """GCS object store for mirrored Serbia source documents."""

    def __init__(self, *, bucket: str, project: str | None = None) -> None:
        """Initialize a Google Cloud Storage upload target."""

        if gcs_storage is None:  # pragma: no cover - dependency guard
            raise ModuleNotFoundError("google-cloud-storage is required for GCSMirrorObjectStore")
        self._bucket_name = bucket
        self._client = gcs_storage.Client(project=project)
        self._bucket = self._client.bucket(bucket)

    def upload_bytes(self, *, object_name: str, content: bytes, content_type: str | None) -> str:
        """Upload bytes and return the gs:// URI."""

        blob = self._bucket.blob(object_name)
        blob.upload_from_string(content, content_type=content_type)
        return f"gs://{self._bucket_name}/{object_name}"


class SerbiaDocumentMirrorService:
    """Mirror resolvable Serbia dataset document links into GCS."""

    def __init__(
        self,
        *,
        repository: SerbiaDatasetRepository,
        fetcher: RemoteDocumentFetcher,
        object_store: MirrorObjectStore,
        gcs_prefix: str,
        timeout_seconds: int,
        max_retries: int,
    ) -> None:
        """Initialize the mirror service."""

        self._repository = repository
        self._fetcher = fetcher
        self._object_store = object_store
        self._gcs_prefix = gcs_prefix.strip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries

    def mirror_pending_rows(
        self,
        *,
        batch_size: int,
        refresh_mode: SerbiaIngestionJobRefreshMode = "pending_only",
    ) -> SerbiaDocumentMirrorSummary:
        """Mirror pending rows and update dataset table lifecycle fields."""

        if batch_size <= 0:
            return SerbiaDocumentMirrorSummary(scanned_rows=0)

        if refresh_mode == "pending_only":
            rows = self._select_pending_rows(batch_size=batch_size)
        else:
            rows = self._repository.list_rows(
                ingestion_readinesses={"ready", "needs_resolver"},
                mirror_statuses={"not_started", "skipped", "mirrored", "failed"},
                limit=batch_size,
            )

        summary = SerbiaDocumentMirrorSummary(scanned_rows=len(rows))
        for row in rows:
            row_result = self._mirror_one_row(row)
            summary.row_results.append(row_result)
            if row_result.mirror_status == "mirrored":
                summary.mirrored_rows += 1
            elif row_result.mirror_status == "failed":
                summary.failed_rows += 1
            else:
                summary.skipped_rows += 1
        return summary

    def _select_pending_rows(self, *, batch_size: int) -> list[SerbiaDatasetRow]:
        """Select a fair pending batch without starving not-started national rows."""

        not_started_rows = self._repository.list_rows(
            ingestion_readinesses={"ready", "needs_resolver"},
            mirror_statuses={"not_started"},
            limit=None,
        )
        failed_rows = self._repository.list_rows(
            ingestion_readinesses={"ready", "needs_resolver"},
            mirror_statuses={"failed"},
            limit=None,
        )

        selected: list[SerbiaDatasetRow] = []
        selected_keys: set[tuple[SerbiaDatasetFamily, str]] = set()

        national_not_started = [row for row in not_started_rows if row.dataset_family == NATIONAL_DATASET_FAMILY]
        non_national_not_started = [row for row in not_started_rows if row.dataset_family != NATIONAL_DATASET_FAMILY]
        national_reserve = _reserved_national_slots(batch_size=batch_size, available_national=len(national_not_started))

        for row in national_not_started[:national_reserve]:
            row_key = (row.dataset_family, row.id)
            selected.append(row)
            selected_keys.add(row_key)
            if len(selected) >= batch_size:
                return selected

        for row in [*non_national_not_started, *national_not_started[national_reserve:]]:
            row_key = (row.dataset_family, row.id)
            if row_key in selected_keys:
                continue
            selected.append(row)
            selected_keys.add(row_key)
            if len(selected) >= batch_size:
                return selected

        for row in failed_rows:
            row_key = (row.dataset_family, row.id)
            if row_key in selected_keys:
                continue
            selected.append(row)
            selected_keys.add(row_key)
            if len(selected) >= batch_size:
                return selected

        return selected

    def mirror_row(
        self,
        *,
        dataset_family: SerbiaDatasetFamily,
        row_id: str,
        refresh_mode: SerbiaIngestionJobRefreshMode = "pending_only",
    ) -> SerbiaDocumentMirrorRowResult:
        """Mirror one specific dataset row."""

        row = self._repository.get_row(dataset_family=dataset_family, row_id=row_id)
        if row is None:
            raise ValueError(f"Serbia dataset row not found: {dataset_family}/{row_id}")
        if row.ingestion_readiness not in {"ready", "needs_resolver"}:
            return SerbiaDocumentMirrorRowResult(
                dataset_family=row.dataset_family,
                row_id=row.id,
                mirror_status="skipped",
                error=(
                    "Row ingestion_readiness is not mirrorable. "
                    f"Expected ready/needs_resolver, got {row.ingestion_readiness}."
                ),
            )
        if refresh_mode == "pending_only" and row.mirror_status in {"mirrored", "skipped"}:
            return SerbiaDocumentMirrorRowResult(
                dataset_family=row.dataset_family,
                row_id=row.id,
                mirror_status="skipped",
                resolved_document_url=row.resolved_document_url,
                gcs_uri=row.gcs_uri,
                error=f"Row already in terminal mirror status: {row.mirror_status}.",
            )
        return self._mirror_one_row(row)

    def _mirror_one_row(self, row: SerbiaDatasetRow) -> SerbiaDocumentMirrorRowResult:
        """Mirror one dataset row and persist status updates."""

        resolved_url = self._resolve_document_url(row)
        if not resolved_url:
            updated = row.model_copy(
                update={
                    "mirror_status": "skipped",
                    "mirror_error": "No resolvable direct document URL.",
                    "ingestion_readiness": "needs_resolver",
                }
            )
            self._repository.upsert_row(updated)
            return SerbiaDocumentMirrorRowResult(
                dataset_family=row.dataset_family,
                row_id=row.id,
                mirror_status="skipped",
                error=updated.mirror_error,
            )

        try:
            fetched = self._fetcher.fetch_document(
                resolved_url,
                timeout_seconds=self._timeout_seconds,
                max_retries=self._max_retries,
            )
            mime_type = _normalize_mime_type(fetched.mime_type)
            extension = _derive_extension(
                url=fetched.final_url,
                mime_type=mime_type,
                content_disposition=fetched.content_disposition,
            )
            object_name = _build_object_name(
                row=row,
                extension=extension,
                gcs_prefix=self._gcs_prefix,
            )
            gcs_uri = self._object_store.upload_bytes(
                object_name=object_name,
                content=fetched.content,
                content_type=mime_type,
            )
            updated = row.model_copy(
                update={
                    "resolved_document_url": fetched.final_url,
                    "url_kind": _url_kind_for_extension(extension),
                    "ingestion_readiness": "ready",
                    "mirror_status": "mirrored",
                    "mirror_error": None,
                    "gcs_uri": gcs_uri,
                    "document_checksum_sha256": hashlib.sha256(fetched.content).hexdigest(),
                    "document_size_bytes": len(fetched.content),
                    "document_mime_type": mime_type,
                }
            )
            self._repository.upsert_row(updated)
            return SerbiaDocumentMirrorRowResult(
                dataset_family=row.dataset_family,
                row_id=row.id,
                mirror_status="mirrored",
                resolved_document_url=fetched.final_url,
                gcs_uri=gcs_uri,
            )
        except Exception as exc:
            updated = row.model_copy(
                update={
                    "mirror_status": "failed",
                    "mirror_error": str(exc),
                }
            )
            self._repository.upsert_row(updated)
            return SerbiaDocumentMirrorRowResult(
                dataset_family=row.dataset_family,
                row_id=row.id,
                mirror_status="failed",
                resolved_document_url=resolved_url,
                error=str(exc),
            )

    def _resolve_document_url(self, row: SerbiaDatasetRow) -> str | None:
        """Resolve a row URL into a direct-download document URL when possible."""

        direct_candidates = [row.resolved_document_url, row.source_url]
        for candidate in direct_candidates:
            if candidate and _looks_document_like(candidate):
                return candidate

        if row.source_url and row.url_kind == "cloud_drive":
            resolved = _resolve_google_drive_url(row.source_url)
            if resolved:
                return resolved

        if row.landing_page_url and row.url_kind == "landing_page":
            discovered = _discover_direct_link_from_landing_page(
                row.landing_page_url,
                fetcher=self._fetcher,
                timeout_seconds=self._timeout_seconds,
                max_retries=self._max_retries,
            )
            if discovered:
                return discovered
            return None

        if row.source_url and row.url_kind in {"direct_document", "office_doc", "archive"}:
            return row.source_url
        return None


def _normalize_mime_type(raw_value: str | None) -> str | None:
    """Normalize MIME values by dropping charset suffixes."""

    if not raw_value:
        return None
    return raw_value.split(";", 1)[0].strip().lower()


def _resolve_google_drive_url(url: str) -> str | None:
    """Convert common Google Drive share links to direct-download URLs."""

    parsed = urlparse(url)
    if "drive.google.com" not in parsed.netloc:
        return None
    match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", parsed.path)
    if match:
        return f"https://drive.google.com/uc?export=download&id={match.group(1)}"
    query_id = parse_qs(parsed.query).get("id")
    if query_id:
        return f"https://drive.google.com/uc?export=download&id={query_id[0]}"
    return None


def _discover_direct_link_from_landing_page(
    landing_page_url: str,
    *,
    fetcher: RemoteDocumentFetcher,
    timeout_seconds: int,
    max_retries: int,
) -> str | None:
    """Extract a likely direct document URL from a landing page."""

    html = fetcher.fetch_text(
        landing_page_url,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )
    pattern = re.compile(r"""href=["']([^"']+\.(?:pdf|docx?|zip|csv|txt))["']""", re.IGNORECASE)
    for match in pattern.finditer(html):
        candidate = unescape(match.group(1)).strip()
        if not candidate:
            continue
        return urljoin(landing_page_url, candidate)
    return None


def _derive_extension(*, url: str, mime_type: str | None, content_disposition: str | None) -> str:
    """Return file extension inferred from URL, headers, or MIME type."""

    if content_disposition:
        filename_match = re.search(r"""filename\*?=(?:UTF-8''|")?([^";]+)""", content_disposition, re.IGNORECASE)
        if filename_match:
            value = filename_match.group(1).strip().strip('"').strip("'")
            parsed_ext = _suffix_from_path(value)
            if parsed_ext:
                return parsed_ext

    parsed_ext = _suffix_from_path(urlparse(url).path)
    if parsed_ext:
        return parsed_ext

    guessed = mimetypes.guess_extension(mime_type or "")
    if guessed:
        return guessed.lstrip(".").lower()
    return "bin"


def _suffix_from_path(path_value: str) -> str | None:
    """Extract and normalize the final suffix from a URL path."""

    match = re.search(r"\.([a-zA-Z0-9]{2,8})$", path_value)
    if not match:
        return None
    return match.group(1).lower()


def _url_kind_for_extension(extension: str) -> str:
    """Map file extension to Serbia URL kind enum values."""

    ext = extension.lower().lstrip(".")
    if ext in {"zip", "rar", "7z", "tar", "tgz"}:
        return "archive"
    if ext in {"doc", "docx", "xls", "xlsx", "ppt", "pptx"}:
        return "office_doc"
    return "direct_document"


def _looks_document_like(url: str) -> bool:
    """Return whether a URL appears to reference a downloadable file."""

    lowered = url.lower()
    return any(ext in lowered for ext in (".pdf", ".doc", ".docx", ".zip", ".csv", ".txt", ".rtf"))


def _slugify(value: str) -> str:
    """Return a lowercase slug for object path construction."""

    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered)
    return lowered.strip("-") or "unknown"


def _build_object_name(*, row: SerbiaDatasetRow, extension: str, gcs_prefix: str) -> str:
    """Build deterministic GCS object names by dataset family and geography."""

    doc_slug = _slugify(row.title)[:96]
    ext = extension.lstrip(".").lower() or "bin"
    year = str(row.year_value) if row.year_value else "unknown"
    category_slug = _slugify(row.category or row.sector or "general")

    if row.dataset_family == "serbia_national_documents":
        suffix = f"national/srb/{category_slug}/{year}/{doc_slug}__{ext}"
    elif row.dataset_family == "serbia_municipal_development_plans":
        municipality_slug = _slugify(row.municipality_name or "unknown-municipality")
        suffix = f"municipal/{municipality_slug}/{category_slug}/{year}/{doc_slug}__{ext}"
    else:
        family_slug = row.dataset_family.replace("serbia_", "")
        suffix = f"projects/serbia/{family_slug}/{row.id}/{doc_slug}__{ext}"

    if gcs_prefix:
        return f"{gcs_prefix}/{suffix}"
    return suffix


def _reserved_national_slots(*, batch_size: int, available_national: int) -> int:
    """Return national rows reserved per batch to avoid starvation."""

    if batch_size <= 0 or available_national <= 0:
        return 0
    reserve = max(1, int(batch_size * NATIONAL_BATCH_RESERVE_RATIO))
    return min(reserve, available_national, batch_size)
