"""agentsdk/persistence/checkpoint.py

Checkpoint data model, CheckpointStore protocol, and InMemoryCheckpointStore.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Checkpoint — serialisable agent state snapshot
# ---------------------------------------------------------------------------


class Checkpoint(BaseModel):
    """Full serialisable snapshot of an agent session at a point in time."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    """Unique identifier for the session this checkpoint belongs to."""

    agent_name: str
    """Matches AgentConfig.name — used to scope file/db storage."""

    history: list[dict]
    """MessageHistory.to_dict_list() output — OpenAI-format message dicts."""

    iteration: int
    """Number of ReAct steps that have run so far in this session."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    """Arbitrary tags: user_id, task_id, stopped_by reason, etc."""

    created_at: datetime = Field(default_factory=_utcnow)
    """Timestamp when this session was first created."""

    updated_at: datetime = Field(default_factory=_utcnow)
    """Timestamp of the most recent save."""

    version: int = 1
    """Monotonically incremented on every save — enables optimistic concurrency checks."""


# ---------------------------------------------------------------------------
# CheckpointStore — storage protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class CheckpointStore(Protocol):
    """Abstract storage backend for checkpoints.

    Implementations must be async-safe.  ``load`` must return ``None`` when
    the session doesn't exist — never raise on missing.
    """

    async def save(self, checkpoint: Checkpoint) -> None:
        """Persist *checkpoint*, overwriting any existing entry for its session_id."""
        ...

    async def load(self, session_id: str) -> Checkpoint | None:
        """Return the checkpoint for *session_id*, or ``None`` if not found."""
        ...

    async def delete(self, session_id: str) -> None:
        """Remove the checkpoint for *session_id*.  No-op if not found."""
        ...

    async def list_sessions(self, agent_name: str | None = None) -> list[str]:
        """Return session IDs, optionally filtered to *agent_name*."""
        ...


# ---------------------------------------------------------------------------
# InMemoryCheckpointStore — dict-backed, single-process
# ---------------------------------------------------------------------------


class InMemoryCheckpointStore:
    """Dict-backed checkpoint store.  Useful for tests and single-process use."""

    def __init__(self) -> None:
        self._store: dict[str, Checkpoint] = {}

    async def save(self, checkpoint: Checkpoint) -> None:
        self._store[checkpoint.session_id] = checkpoint

    async def load(self, session_id: str) -> Checkpoint | None:
        return self._store.get(session_id)

    async def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    async def list_sessions(self, agent_name: str | None = None) -> list[str]:
        if agent_name is None:
            return list(self._store.keys())
        return [
            sid
            for sid, cp in self._store.items()
            if cp.agent_name == agent_name
        ]
