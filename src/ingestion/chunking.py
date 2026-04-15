"""Source ingestion, parsing, and chunking pipeline logic."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from statistics import mean, pstdev

from src.embeddings.client import EmbeddingClient


@dataclass(frozen=True)
class SemanticChunk:
    """Structured semantic chunk before schema conversion."""

    text: str
    token_count: int
    semantic_group_id: int
    section_path: list[str]
    body_text: str
    header_text: str


@dataclass(frozen=True)
class SemanticChunkingConfig:
    """Config for semantic chunking."""

    max_tokens: int = 180
    overlap_tokens: int = 24
    min_chunk_tokens: int = 40
    breakpoint_threshold_type: str = "percentile"
    breakpoint_threshold_amount: float = 90.0


@dataclass(frozen=True)
class SectionBlock:
    """Logical section extracted from a document with heading context."""

    text: str
    section_path: list[str]


def estimate_token_count(text: str) -> int:
    """Estimate token count using a conservative whitespace tokenizer."""

    return len([token for token in text.strip().split() if token])


def _normalize_heading(text: str) -> str:
    """Normalize a heading candidate into compact single-line form."""

    return re.sub(r"\s+", " ", text.strip(" #:-")).strip()


def _heading_level(paragraph: str) -> tuple[int, str] | None:
    """Return a heading level and normalized label when a paragraph looks like a heading."""

    stripped = paragraph.strip()
    markdown_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
    if markdown_match:
        return len(markdown_match.group(1)), _normalize_heading(markdown_match.group(2))

    numbered_match = re.match(r"^(\d+(?:\.\d+)*)\s+(.+)$", stripped)
    if numbered_match:
        level = numbered_match.group(1).count(".") + 1
        return level, _normalize_heading(numbered_match.group(2))

    words = stripped.split()
    if 0 < len(words) <= 12 and len(stripped) <= 100:
        alpha_only = re.sub(r"[^A-Za-z]+", "", stripped)
        if alpha_only and stripped.upper() == stripped:
            return 1, _normalize_heading(stripped.title())
    return None


def _split_sections(text: str) -> list[SectionBlock]:
    """Split text into coarse sections and retain heading hierarchy."""

    normalized = text.replace("\r\n", "\n")
    if not normalized.strip():
        return []

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n{2,}", normalized) if paragraph.strip()]
    section_stack: list[str] = []
    blocks: list[SectionBlock] = []

    for paragraph in paragraphs:
        heading_info = _heading_level(paragraph)
        if heading_info and "\n" not in paragraph:
            level, label = heading_info
            if not label:
                continue
            while len(section_stack) >= level:
                section_stack.pop()
            section_stack.append(label)
            continue

        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if lines:
            first_line_heading = _heading_level(lines[0])
            if first_line_heading and len(lines) > 1:
                level, label = first_line_heading
                while len(section_stack) >= level:
                    section_stack.pop()
                section_stack.append(label)
                paragraph = "\n".join(lines[1:]).strip()
        if paragraph:
            blocks.append(SectionBlock(text=paragraph, section_path=list(section_stack)))
    return blocks


def _split_sentences(text: str) -> list[str]:
    """Split text into sentence-like units while preserving headings and bullets."""

    normalized = text.replace("\r\n", "\n")
    normalized = re.sub(r"\n(?=[#*\-])", ".\n", normalized)
    rows = re.split(r"(?<=[.!?])\s+|\n+", normalized)
    return [row.strip() for row in rows if row and row.strip()]


def _cosine_distance(left: list[float], right: list[float]) -> float:
    """Return cosine distance between two vectors."""

    if not left or not right:
        return 0.0
    numerator = sum(lv * rv for lv, rv in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    similarity = numerator / (left_norm * right_norm)
    similarity = max(min(similarity, 1.0), -1.0)
    return 1.0 - similarity


def _percentile(values: list[float], percentile: float) -> float:
    """Return a percentile using linear interpolation."""

    if not values:
        return 1.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = max(0.0, min(100.0, percentile)) / 100.0 * (len(sorted_values) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return sorted_values[lower]
    weight = rank - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _iqr(values: list[float]) -> tuple[float, float]:
    """Return first and third quartiles."""

    return _percentile(values, 25.0), _percentile(values, 75.0)


def _resolve_breakpoint_threshold(distances: list[float], threshold_type: str, amount: float) -> float:
    """Resolve the distance threshold that marks semantic boundaries."""

    if not distances:
        return 1.0
    if threshold_type == "percentile":
        return _percentile(distances, amount)
    if threshold_type == "standard_deviation":
        return mean(distances) + (pstdev(distances) * amount)
    if threshold_type == "interquartile":
        q1, q3 = _iqr(distances)
        return q3 + ((q3 - q1) * amount)
    raise ValueError(f"Unsupported breakpoint_threshold_type: {threshold_type}")


def _window_sentences(sentences: list[str], center: int, radius: int = 1) -> str:
    """Return a small semantic neighborhood around a sentence."""

    start = max(0, center - radius)
    end = min(len(sentences), center + radius + 1)
    return " ".join(sentences[start:end])


def _merge_short_chunks(chunks: list[str], min_chunk_tokens: int) -> list[str]:
    """Merge undersized chunks into neighbors."""

    if not chunks:
        return []
    merged: list[str] = []
    for chunk in chunks:
        if merged and estimate_token_count(chunk) < min_chunk_tokens:
            merged[-1] = f"{merged[-1]} {chunk}".strip()
        else:
            merged.append(chunk)
    return merged


def _enforce_token_budget(text: str, *, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Split oversized semantic chunks into bounded windows."""

    tokens = text.split()
    if not tokens:
        return []
    if len(tokens) <= max_tokens:
        return [" ".join(tokens)]

    output: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(len(tokens), start + max_tokens)
        window = tokens[start:end]
        if window:
            output.append(" ".join(window))
        if end == len(tokens):
            break
        start = end - overlap_tokens
    return output


def _build_header_lines(*, document_title: str, source_type: str, category: str | None, section_path: list[str]) -> list[str]:
    """Build a deterministic contextual chunk header."""

    lines = [f"Document Title: {document_title}", f"Source Type: {source_type}"]
    if category:
        lines.append(f"Category: {category}")
    if section_path:
        lines.append(f"Section Path: {' > '.join(section_path)}")
    return lines


def build_contextual_chunk_text(
    *,
    document_title: str,
    source_type: str,
    category: str | None,
    section_path: list[str],
    body_text: str,
) -> tuple[str, str]:
    """Return header text and final chunk text for embedding and display."""

    header_text = "\n".join(
        _build_header_lines(
            document_title=document_title,
            source_type=source_type,
            category=category,
            section_path=section_path,
        )
    ).strip()
    if not header_text:
        return "", body_text
    return header_text, f"{header_text}\n\n{body_text}".strip()


def chunk_text_semantic(
    text: str,
    *,
    embedding_client: EmbeddingClient,
    document_title: str,
    source_type: str,
    category: str | None = None,
    config: SemanticChunkingConfig | None = None,
) -> list[SemanticChunk]:
    """Chunk text using sentence-embedding breakpoints inspired by the notebook logic."""

    effective = config or SemanticChunkingConfig()
    if effective.max_tokens <= effective.overlap_tokens:
        raise ValueError("max_tokens must be greater than overlap_tokens.")

    sections = _split_sections(text)
    if not sections:
        return []

    semantic_chunks: list[SemanticChunk] = []
    semantic_group_id = 0
    for section in sections:
        sentences = _split_sentences(section.text)
        if not sentences:
            continue
        if len(sentences) == 1:
            sentence_chunks = _enforce_token_budget(
                sentences[0],
                max_tokens=effective.max_tokens,
                overlap_tokens=effective.overlap_tokens,
            )
            for text_chunk in sentence_chunks:
                header_text, contextual_text = build_contextual_chunk_text(
                    document_title=document_title,
                    source_type=source_type,
                    category=category,
                    section_path=section.section_path,
                    body_text=text_chunk,
                )
                semantic_chunks.append(
                    SemanticChunk(
                        text=contextual_text,
                        token_count=estimate_token_count(text_chunk),
                        semantic_group_id=semantic_group_id,
                        section_path=section.section_path,
                        body_text=text_chunk,
                        header_text=header_text,
                    )
                )
            semantic_group_id += 1
            continue

        sentence_windows = [_window_sentences(sentences, idx) for idx in range(len(sentences))]
        embeddings = embedding_client.embed_texts(sentence_windows)
        distances = [
            _cosine_distance(embeddings[idx], embeddings[idx + 1])
            for idx in range(len(embeddings) - 1)
        ]
        threshold = _resolve_breakpoint_threshold(
            distances,
            effective.breakpoint_threshold_type,
            effective.breakpoint_threshold_amount,
        )
        split_points = {
            idx + 1
            for idx, distance in enumerate(distances)
            if distance >= threshold and distance > 0
        }

        sentence_groups: list[str] = []
        start_idx = 0
        for idx in range(1, len(sentences)):
            if idx in split_points:
                sentence_groups.append(" ".join(sentences[start_idx:idx]).strip())
                start_idx = idx
        sentence_groups.append(" ".join(sentences[start_idx:]).strip())
        sentence_groups = _merge_short_chunks(sentence_groups, effective.min_chunk_tokens)

        for group in sentence_groups:
            for text_chunk in _enforce_token_budget(
                group,
                max_tokens=effective.max_tokens,
                overlap_tokens=effective.overlap_tokens,
            ):
                header_text, contextual_text = build_contextual_chunk_text(
                    document_title=document_title,
                    source_type=source_type,
                    category=category,
                    section_path=section.section_path,
                    body_text=text_chunk,
                )
                semantic_chunks.append(
                    SemanticChunk(
                        text=contextual_text,
                        token_count=estimate_token_count(text_chunk),
                        semantic_group_id=semantic_group_id,
                        section_path=section.section_path,
                        body_text=text_chunk,
                        header_text=header_text,
                    )
                )
            semantic_group_id += 1

    return semantic_chunks


def chunk_text(
    text: str,
    *,
    max_tokens: int = 180,
    overlap_tokens: int = 24,
) -> list[str]:
    """Legacy token-window chunking retained for compatibility tests."""

    if max_tokens <= overlap_tokens:
        raise ValueError("max_tokens must be greater than overlap_tokens.")

    sections = _split_sections(text)
    if not sections:
        return []

    output: list[str] = []
    for section in sections:
        output.extend(_enforce_token_budget(section.text, max_tokens=max_tokens, overlap_tokens=overlap_tokens))
    return output
