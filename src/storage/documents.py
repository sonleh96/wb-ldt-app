"""Document object storage abstractions for source ingestion."""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator, Protocol

from src.config.settings import Settings

try:  # pragma: no cover - optional dependency path
    from google.cloud import storage as gcs_storage
except ModuleNotFoundError:  # pragma: no cover - optional dependency path
    gcs_storage = None  # type: ignore[assignment]


def is_gcs_uri(uri: str) -> bool:
    """Return whether a URI points to Google Cloud Storage."""

    return uri.strip().lower().startswith("gs://")


def parse_gcs_uri(uri: str) -> tuple[str, str]:
    """Return bucket and object name from a gs:// URI."""

    normalized = uri.strip()
    if not is_gcs_uri(normalized):
        raise ValueError(f"Not a GCS URI: {uri}")
    remainder = normalized[5:]
    bucket, separator, object_name = remainder.partition("/")
    if not bucket or not separator or not object_name:
        raise ValueError("GCS URI must use gs://bucket/object format.")
    return bucket, object_name


def filename_from_uri(uri: str) -> str:
    """Return the terminal filename component from a local or GCS URI."""

    normalized = uri.strip()
    if is_gcs_uri(normalized):
        _, object_name = parse_gcs_uri(normalized)
        return object_name.rstrip("/").rsplit("/", 1)[-1]
    return Path(normalized).expanduser().name


def suffix_from_uri(uri: str) -> str:
    """Return the lowercase filename suffix from a local or GCS URI."""

    return Path(filename_from_uri(uri)).suffix.lower()


class DocumentStore(Protocol):
    """Repository interface for source document object access."""

    def exists(self, uri: str) -> bool:
        """Return whether a document URI exists."""

    def as_local_path(self, uri: str) -> AbstractContextManager[Path]:
        """Yield a local filesystem path for parser libraries."""


class LocalDocumentStore:
    """Document store for local filesystem source files."""

    def exists(self, uri: str) -> bool:
        """Return whether a local file exists."""

        if is_gcs_uri(uri):
            return False
        return Path(uri).expanduser().is_file()

    @contextmanager
    def as_local_path(self, uri: str) -> Iterator[Path]:
        """Yield a local source path."""

        if is_gcs_uri(uri):
            raise FileNotFoundError("GCS URI cannot be resolved by LocalDocumentStore.")
        path = Path(uri).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Source URI must point to an existing local file: {uri}")
        yield path


class GCSDocumentStore:
    """Document store backed by Google Cloud Storage."""

    def __init__(
        self,
        *,
        project: str | None = None,
        allowed_bucket: str | None = None,
        allowed_prefix: str = "",
    ) -> None:
        """Initialize the GCS document store."""

        if gcs_storage is None:  # pragma: no cover - dependency guard
            raise ModuleNotFoundError("google-cloud-storage is required when document_store_backend=gcs")
        self._client = gcs_storage.Client(project=project)
        self._allowed_bucket = allowed_bucket
        self._allowed_prefix = allowed_prefix.strip("/")

    def _validate_location(self, *, bucket_name: str, object_name: str) -> None:
        """Validate an object location against configured bucket/prefix limits."""

        if self._allowed_bucket and bucket_name != self._allowed_bucket:
            raise ValueError(f"GCS bucket {bucket_name} does not match configured bucket {self._allowed_bucket}.")
        if self._allowed_prefix and not object_name.startswith(f"{self._allowed_prefix}/"):
            raise ValueError(
                f"GCS object {object_name} is outside configured prefix {self._allowed_prefix}/."
            )

    def exists(self, uri: str) -> bool:
        """Return whether a GCS object exists."""

        bucket_name, object_name = parse_gcs_uri(uri)
        try:
            self._validate_location(bucket_name=bucket_name, object_name=object_name)
        except ValueError:
            return False
        bucket = self._client.bucket(bucket_name)
        return bucket.blob(object_name).exists()

    @contextmanager
    def as_local_path(self, uri: str) -> Iterator[Path]:
        """Download a GCS object to a temporary local path for parsing."""

        bucket_name, object_name = parse_gcs_uri(uri)
        self._validate_location(bucket_name=bucket_name, object_name=object_name)
        filename = filename_from_uri(uri)
        with TemporaryDirectory(prefix="ldt-gcs-source-") as tmp_dir:
            local_path = Path(tmp_dir) / filename
            bucket = self._client.bucket(bucket_name)
            bucket.blob(object_name).download_to_filename(str(local_path))
            yield local_path


class RoutedDocumentStore:
    """Route local and GCS document access through configured stores."""

    def __init__(self, *, local_store: DocumentStore, gcs_store: DocumentStore | None = None) -> None:
        """Initialize the routed document store."""

        self._local_store = local_store
        self._gcs_store = gcs_store

    def exists(self, uri: str) -> bool:
        """Return whether a document URI exists in its backing store."""

        if is_gcs_uri(uri):
            if self._gcs_store is None:
                return False
            return self._gcs_store.exists(uri)
        return self._local_store.exists(uri)

    @contextmanager
    def as_local_path(self, uri: str) -> Iterator[Path]:
        """Yield a local parser path for local or GCS-backed documents."""

        if is_gcs_uri(uri):
            if self._gcs_store is None:
                raise FileNotFoundError("GCS URI cannot be resolved because GCS document storage is not configured.")
            with self._gcs_store.as_local_path(uri) as path:
                yield path
            return
        with self._local_store.as_local_path(uri) as path:
            yield path


def build_document_store(settings: Settings) -> DocumentStore:
    """Build the configured document store."""

    local_store = LocalDocumentStore()
    backend = settings.document_store_backend.lower()
    if backend == "local":
        return RoutedDocumentStore(local_store=local_store)
    if backend == "gcs":
        return RoutedDocumentStore(
            local_store=local_store,
            gcs_store=GCSDocumentStore(
                project=settings.gcp_project,
                allowed_bucket=settings.gcs_bucket,
                allowed_prefix=settings.gcs_prefix,
            ),
        )
    raise ValueError(f"Unsupported document_store_backend: {settings.document_store_backend}")
