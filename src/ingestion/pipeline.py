"""Source ingestion, parsing, and chunking pipeline logic."""

import csv
import html
import re
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from src.embeddings.client import EmbeddingClient
from src.ingestion.chunking import SemanticChunkingConfig, chunk_text_semantic
from src.ingestion.parsers import parse_docx_to_markdownish, parse_pdf_to_markdown
from src.schemas.source_metadata import IngestionResult, SourceChunk
from src.storage.documents import DocumentStore, LocalDocumentStore, suffix_from_uri
from src.storage.sources import SourceRepository


class IngestionPipeline:
    """
    Ingestion pipeline with pluggable parsing and chunking stages.
    """

    def __init__(
        self,
        source_repository: SourceRepository,
        *,
        embedding_client: EmbeddingClient,
        document_store: DocumentStore | None = None,
        chunking_config: SemanticChunkingConfig | None = None,
    ) -> None:
        """Initialize the instance and its dependencies."""
        self._source_repository = source_repository
        self._embedding_client = embedding_client
        self._document_store = document_store or LocalDocumentStore()
        self._chunking_config = chunking_config or SemanticChunkingConfig()

    def ingest_source(self, source_id: str) -> IngestionResult:
        """Ingest source."""
        source = self._source_repository.get_source(source_id)
        if source is None:
            raise ValueError(f"source_id={source_id} not found")

        parsed_text, parser_used = self._parse_source(source.uri, mime_type=source.mime_type)
        chunk_rows = chunk_text_semantic(
            parsed_text,
            embedding_client=self._embedding_client,
            document_title=source.title,
            source_type=source.source_type,
            category=source.category,
            config=self._chunking_config,
        )
        chunk_embeddings = self._embedding_client.embed_texts([row.text for row in chunk_rows])
        chunks = [
            SourceChunk(
                chunk_id=f"{source.source_id}:{index}",
                source_id=source.source_id,
                chunk_index=index,
                text=row.text,
                body_text=row.body_text,
                header_text=row.header_text,
                section_path=row.section_path,
                token_count=row.token_count,
                embedding=chunk_embeddings[index],
                embedding_model=self._embedding_client.model_name,
                semantic_group_id=row.semantic_group_id,
                municipality_id=source.municipality_id,
                category=source.category,
                source_type=source.source_type,
            )
            for index, row in enumerate(chunk_rows)
        ]

        self._source_repository.replace_chunks(source.source_id, chunks)
        return IngestionResult(
            source_id=source.source_id,
            parsed_text_length=len(parsed_text),
            chunk_count=len(chunks),
            parser_used=parser_used,
        )

    def _parse_source(self, uri: str, *, mime_type: str | None = None) -> tuple[str, str]:
        """Internal helper to parse source."""
        suffix = self._suffix_from_uri_or_mime(uri=uri, mime_type=mime_type)

        with self._document_store.as_local_path(uri) as path:
            if suffix == ".zip":
                return self._parse_zip_archive(path), "zip_archive_parser"
            parsed = self._parse_path_by_suffix(path=path, suffix=suffix)
            if parsed is not None:
                return parsed
            sniffed_suffix = self._sniff_suffix_from_binary(path)
            if sniffed_suffix == ".zip":
                return self._parse_zip_archive(path), "zip_archive_parser"
            if sniffed_suffix:
                parsed = self._parse_path_by_suffix(path=path, suffix=sniffed_suffix)
                if parsed is not None:
                    return parsed

            return self._parse_binary_placeholder(path), "binary_placeholder_parser"

    @staticmethod
    def _suffix_from_uri_or_mime(*, uri: str, mime_type: str | None) -> str:
        """Return best-effort suffix from URI first, then MIME type fallback."""

        suffix = suffix_from_uri(uri)
        if suffix:
            return suffix

        normalized_mime = (mime_type or "").split(";", 1)[0].strip().lower()
        mime_to_suffix = {
            "application/pdf": ".pdf",
            "application/msword": ".doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/zip": ".zip",
            "application/x-zip-compressed": ".zip",
            "multipart/x-zip": ".zip",
            "text/csv": ".csv",
            "application/csv": ".csv",
            "text/plain": ".txt",
            "text/markdown": ".md",
            "text/html": ".html",
        }
        return mime_to_suffix.get(normalized_mime, "")

    def _parse_path_by_suffix(self, *, path: Path, suffix: str) -> tuple[str, str] | None:
        """Parse one local file by suffix, returning text and parser id."""

        if suffix == ".csv":
            return self._parse_csv(path), "csv_parser"
        if suffix == ".pdf":
            return parse_pdf_to_markdown(path), "pymupdf4llm_markdown_parser"
        if suffix == ".docx":
            return parse_docx_to_markdownish(path), "mammoth_docx_parser"
        if suffix in {".txt", ".md"}:
            return path.read_text(encoding="utf-8"), "text_parser"
        if suffix in {".html", ".htm"}:
            return self._parse_html(path), "html_text_parser"
        return None

    @staticmethod
    def _sniff_suffix_from_binary(path: Path) -> str:
        """Infer parseable suffix from binary signatures when URI/MIME are unreliable."""

        try:
            with path.open("rb") as handle:
                header = handle.read(4096)
        except OSError:
            return ""

        if header.startswith(b"%PDF-"):
            return ".pdf"
        if header.startswith(b"PK"):
            try:
                with zipfile.ZipFile(path, "r") as archive:
                    names = [name for name in archive.namelist() if name]
            except zipfile.BadZipFile:
                return ""
            if any(name.startswith("word/") for name in names):
                return ".docx"
            return ".zip"

        lowered = header.lstrip().lower()
        if lowered.startswith((b"<!doctype html", b"<html")):
            return ".html"
        if not header:
            return ""
        if b"\x00" not in header:
            return ".txt"
        return ""

    def _parse_zip_archive(self, path: Path) -> str:
        """Extract parseable files from a ZIP archive and combine parsed content."""

        try:
            archive = zipfile.ZipFile(path, "r")
        except zipfile.BadZipFile as exc:
            raise ValueError(f"Invalid ZIP archive: {path.name}") from exc

        parsed_parts: list[str] = []
        errors: list[str] = []
        with archive:
            members = [info for info in archive.infolist() if not info.is_dir()]
            with TemporaryDirectory(prefix="ldt-zip-") as tmp_dir:
                tmp_path = Path(tmp_dir)
                for member in members:
                    member_name = member.filename
                    member_suffix = suffix_from_uri(member_name)
                    if member_suffix not in {".pdf", ".docx", ".csv", ".txt", ".md", ".html", ".htm"}:
                        continue

                    local_name = Path(member_name).name or f"member-{member.CRC}{member_suffix}"
                    local_path = tmp_path / local_name
                    try:
                        with archive.open(member, "r") as src, local_path.open("wb") as dst:
                            dst.write(src.read())
                        parsed = self._parse_path_by_suffix(path=local_path, suffix=member_suffix)
                        if parsed is None:
                            continue
                        member_text, parser_used = parsed
                        if member_text.strip():
                            parsed_parts.append(
                                f"## ZIP Member: {member_name}\nParser: {parser_used}\n\n{member_text.strip()}"
                            )
                    except Exception as exc:  # pragma: no cover - depends on archive contents
                        errors.append(f"{member_name}: {exc}")

        if parsed_parts:
            return "\n\n".join(parsed_parts).strip()
        if errors:
            raise ValueError(f"ZIP archive had parseable members but all failed: {' | '.join(errors[:3])}")
        raise ValueError("ZIP archive contains no parseable members (.pdf/.docx/.csv/.txt/.md/.html).")

    @staticmethod
    def _parse_html(path: Path) -> str:
        """Convert an HTML file to plain text while preserving basic structure."""

        raw_html = path.read_text(encoding="utf-8", errors="ignore")
        without_scripts = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw_html)
        without_styles = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", without_scripts)
        line_breaks = re.sub(r"(?is)<br\\s*/?>", "\n", without_styles)
        block_breaks = re.sub(r"(?is)</(p|div|section|article|li|h1|h2|h3|h4|h5|h6|tr)>", "\n", line_breaks)
        no_tags = re.sub(r"(?is)<[^>]+>", " ", block_breaks)
        text = html.unescape(no_tags)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        cleaned = text.strip()
        if not cleaned:
            raise ValueError(f"HTML parser returned no text for {path.name}.")
        return cleaned

    @staticmethod
    def _parse_csv(path: Path) -> str:
        """Parse CSV rows into schema-aware textual records for embedding."""

        lines: list[str] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            rows = [[cell.strip() for cell in row] for row in reader]
        if not rows:
            return ""

        header = [IngestionPipeline._normalize_csv_label(cell, fallback=f"column_{index + 1}") for index, cell in enumerate(rows[0])]
        data_rows = rows[1:] if IngestionPipeline._looks_like_header(rows[0], rows[1:]) else rows
        if data_rows:
            lines.append(f"Dataset Columns: {', '.join(header)}")
        for row_index, row in enumerate(data_rows, start=1):
            lines.append(
                IngestionPipeline._render_csv_row(
                    row=row,
                    header=header,
                    row_index=row_index,
                )
            )
        return "\n".join(lines)

    @staticmethod
    def _normalize_csv_label(value: str, *, fallback: str) -> str:
        """Normalize a CSV column label into a compact semantic field name."""

        cleaned = re.sub(r"\s+", " ", value.strip())
        return cleaned if cleaned else fallback

    @staticmethod
    def _looks_like_header(first_row: list[str], remaining_rows: list[list[str]]) -> bool:
        """Heuristically detect whether the first CSV row is a header row."""

        if not first_row:
            return False
        normalized = [cell.strip() for cell in first_row]
        if any(not cell for cell in normalized):
            return False
        if remaining_rows:
            second_row = remaining_rows[0]
            numeric_first = sum(IngestionPipeline._is_numeric_like(cell) for cell in normalized)
            numeric_second = sum(IngestionPipeline._is_numeric_like(cell) for cell in second_row)
            if numeric_first == 0 and numeric_second > 0:
                return True
        return len(set(normalized)) == len(normalized)

    @staticmethod
    def _is_numeric_like(value: str) -> bool:
        """Return whether a value looks numeric after light normalization."""

        candidate = value.strip().replace(",", "").replace("%", "")
        if not candidate:
            return False
        try:
            float(candidate)
        except ValueError:
            return False
        return True

    @staticmethod
    def _render_csv_row(*, row: list[str], header: list[str], row_index: int) -> str:
        """Render a CSV row as labeled field-value statements."""

        field_lines: list[str] = []
        for index, label in enumerate(header):
            value = row[index].strip() if index < len(row) else ""
            if not value:
                continue
            field_lines.append(f"{label}: {value}")
        if not field_lines:
            field_lines.append("Row is empty.")
        return f"### Row {row_index}\n" + "\n".join(field_lines)

    @staticmethod
    def _parse_binary_placeholder(path: Path) -> str:
        """Internal helper to parse binary placeholder."""
        payload_size = path.stat().st_size
        return f"Unsupported parser for {path.name}. Binary size: {payload_size} bytes."
