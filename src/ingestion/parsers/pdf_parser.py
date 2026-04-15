"""PDF parsing helpers backed by PyMuPDF4LLM."""

from __future__ import annotations

from pathlib import Path

try:  # pragma: no cover - optional dependency path
    import pymupdf4llm
except ModuleNotFoundError:  # pragma: no cover - compatibility for lean test environments
    pymupdf4llm = None  # type: ignore[assignment]


def _coerce_markdown_output(payload: object) -> str:
    """Normalize PyMuPDF4LLM output into one markdown string."""

    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        rows: list[str] = []
        for item in payload:
            if isinstance(item, str):
                rows.append(item)
            elif isinstance(item, dict):
                text_value = item.get("text") or item.get("markdown") or item.get("content") or ""
                rows.append(str(text_value))
            else:
                rows.append(str(item))
        return "\n\n".join(row.strip() for row in rows if row and str(row).strip()).strip()
    if isinstance(payload, dict):
        for key in ("text", "markdown", "content"):
            if key in payload and str(payload[key]).strip():
                return str(payload[key]).strip()
    return str(payload).strip()


def parse_pdf_to_markdown(path: Path) -> str:
    """Parse a PDF into markdown text using PyMuPDF4LLM."""

    if pymupdf4llm is None:
        raise ModuleNotFoundError(
            "pymupdf4llm is required for PDF parsing. Install project dependencies before ingesting PDF files."
        )
    markdown = pymupdf4llm.to_markdown(str(path))
    normalized = _coerce_markdown_output(markdown)
    if not normalized:
        raise ValueError(f"PyMuPDF4LLM returned no markdown for {path.name}.")
    return normalized
