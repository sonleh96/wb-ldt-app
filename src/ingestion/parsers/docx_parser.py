"""DOCX parsing helpers backed by Mammoth."""

from __future__ import annotations

import html
import re
from pathlib import Path

try:  # pragma: no cover - optional dependency path
    import mammoth
except ModuleNotFoundError:  # pragma: no cover - compatibility for lean test environments
    mammoth = None  # type: ignore[assignment]


def _strip_inline_tags(value: str) -> str:
    """Remove inline HTML tags from a text fragment."""

    return re.sub(r"<[^>]+>", "", value)


def _replace_heading(match: re.Match[str]) -> str:
    """Convert HTML headings into markdown headings."""

    level = int(match.group(1))
    heading_text = html.unescape(_strip_inline_tags(match.group(2))).strip()
    return f"\n\n{'#' * level} {heading_text}\n\n" if heading_text else "\n\n"


def _replace_list_item(match: re.Match[str]) -> str:
    """Convert list items into markdown bullets."""

    item_text = html.unescape(_strip_inline_tags(match.group(1))).strip()
    return f"- {item_text}\n" if item_text else ""


def _html_to_markdownish(value: str) -> str:
    """Convert Mammoth HTML output into markdown-like structured text."""

    converted = value
    converted = re.sub(r"(?is)<h([1-6])[^>]*>(.*?)</h\1>", _replace_heading, converted)
    converted = re.sub(r"(?is)<li[^>]*>(.*?)</li>", _replace_list_item, converted)
    converted = re.sub(r"(?is)<br\s*/?>", "\n", converted)
    converted = re.sub(r"(?is)</p>|</div>|</section>|</article>|</table>|</tr>", "\n\n", converted)
    converted = re.sub(r"(?is)<p[^>]*>|<div[^>]*>|<section[^>]*>|<article[^>]*>|<table[^>]*>|<tr[^>]*>", "", converted)
    converted = re.sub(r"(?is)<td[^>]*>|<th[^>]*>", "", converted)
    converted = re.sub(r"(?is)</td>|</th>", " | ", converted)
    converted = re.sub(r"(?is)<[^>]+>", "", converted)
    converted = html.unescape(converted)
    converted = re.sub(r"[ \t]+\n", "\n", converted)
    converted = re.sub(r"\n{3,}", "\n\n", converted)
    return converted.strip()


def parse_docx_to_markdownish(path: Path) -> str:
    """Parse a DOCX file into markdown-like text using Mammoth."""

    if mammoth is None:
        raise ModuleNotFoundError(
            "mammoth is required for DOCX parsing. Install project dependencies before ingesting DOCX files."
        )
    with path.open("rb") as handle:
        result = mammoth.convert_to_html(handle)
    markdownish = _html_to_markdownish(result.value)
    if not markdownish:
        raise ValueError(f"Mammoth returned no text for {path.name}.")
    return markdownish
