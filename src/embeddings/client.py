"""Embedding client abstractions and runtime implementations."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

try:
    from openai import OpenAI
except ModuleNotFoundError:  # pragma: no cover - compatibility for lean test environments
    OpenAI = None  # type: ignore[assignment]

from src.config.settings import Settings


def _normalize(vector: list[float]) -> list[float]:
    """Return a unit-normalized vector when possible."""

    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric tokens."""

    return re.findall(r"[a-z0-9]+", text.lower())


class EmbeddingClient:
    """Protocol-like base class for embedding clients."""

    model_name: str

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for a list of texts."""

        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        """Return an embedding for a single query."""

        return self.embed_texts([text])[0]


@dataclass
class DeterministicEmbeddingClient(EmbeddingClient):
    """Offline-safe hashed embedding client used for tests and local fallback."""

    dimensions: int = 256
    model_name: str = "deterministic-hash-v1"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return deterministic embeddings derived from token hashes."""

        rows: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for token in _tokenize(text):
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                for idx in range(0, min(16, len(digest))):
                    slot = (digest[idx] + idx * 13) % self.dimensions
                    sign = 1.0 if digest[idx] % 2 == 0 else -1.0
                    vector[slot] += sign
            rows.append(_normalize(vector))
        return rows


@dataclass
class OpenAIEmbeddingClient(EmbeddingClient):
    """OpenAI-backed embedding client."""

    client: OpenAI
    model_name: str
    dimensions: int | None = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for a list of texts."""

        if not texts:
            return []
        request_payload: dict[str, object] = {
            "model": self.model_name,
            "input": texts,
        }
        if self.dimensions is not None:
            request_payload["dimensions"] = self.dimensions
        response = self.client.embeddings.create(**request_payload)
        return [list(item.embedding) for item in response.data]


def build_embedding_client(settings: Settings) -> EmbeddingClient:
    """Build the configured embedding client."""

    if settings.embedding_provider == "openai":
        if OpenAI is None:
            raise ModuleNotFoundError("openai is required when embedding_provider=openai")
        if not settings.openai_api_key:
            raise ValueError("LDT_OPENAI_API_KEY is required when embedding_provider=openai")
        client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        return OpenAIEmbeddingClient(
            client=client,
            model_name=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    return DeterministicEmbeddingClient(dimensions=settings.embedding_dimensions)
