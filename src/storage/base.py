"""Storage abstractions and in-memory repository implementations."""

from typing import Protocol


class Repository(Protocol):
    """Marker protocol for repository interfaces."""
