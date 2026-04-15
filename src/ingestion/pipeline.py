"""Source ingestion, parsing, and chunking pipeline logic."""

import csv
import re
from pathlib import Path

from src.embeddings.client import EmbeddingClient
from src.ingestion.chunking import SemanticChunkingConfig, chunk_text_semantic
from src.ingestion.parsers import parse_docx_to_markdownish, parse_pdf_to_markdown
from src.schemas.source_metadata import IngestionResult, SourceChunk
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
        chunking_config: SemanticChunkingConfig | None = None,
    ) -> None:
        """Initialize the instance and its dependencies."""
        self._source_repository = source_repository
        self._embedding_client = embedding_client
        self._chunking_config = chunking_config or SemanticChunkingConfig()

    def ingest_source(self, source_id: str) -> IngestionResult:
        """Ingest source."""
        source = self._source_repository.get_source(source_id)
        if source is None:
            raise ValueError(f"source_id={source_id} not found")

        parsed_text, parser_used = self._parse_source(source.uri)
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

    def _parse_source(self, uri: str) -> tuple[str, str]:
        """Internal helper to parse source."""
        path = Path(uri)
        suffix = path.suffix.lower()

        if suffix == ".csv":
            return self._parse_csv(path), "csv_parser"
        if suffix == ".pdf":
            return parse_pdf_to_markdown(path), "pymupdf4llm_markdown_parser"
        if suffix == ".docx":
            return parse_docx_to_markdownish(path), "mammoth_docx_parser"
        if suffix in {".txt", ".md"}:
            return path.read_text(encoding="utf-8"), "text_parser"

        return self._parse_binary_placeholder(path), "binary_placeholder_parser"

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
