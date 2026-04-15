"""Typed schema definitions used across API and workflow boundaries."""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

def utcnow() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


class RunState(str, Enum):
    """Typed schema for RunState."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunTransition(BaseModel):
    """Typed schema for RunTransition."""
    from_state: RunState
    to_state: RunState
    changed_at: datetime = Field(default_factory=utcnow)
    note: str | None = None


class RunRecord(BaseModel):
    """Typed schema for RunRecord."""
    run_id: str
    request: dict[str, object]
    state: RunState
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    current_node: str = "create_run"
    result: dict = Field(default_factory=dict)
    error_message: str | None = None
    transitions: list[RunTransition] = Field(default_factory=list)
