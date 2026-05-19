"""agentsdk/persistence — Persistence & State Layer.

Public surface:

    Checkpoint              — Pydantic snapshot of a full agent session
    CheckpointStore         — Protocol that storage backends implement
    InMemoryCheckpointStore — Dict-backed store (tests / single-process)
    FileCheckpointStore     — JSON-file-backed store
    SessionManager          — High-level interface used by Agent
"""

from agentsdk.persistence.checkpoint import (
    Checkpoint,
    CheckpointStore,
    InMemoryCheckpointStore,
)
from agentsdk.persistence.file_store import FileCheckpointStore
from agentsdk.persistence.session import SessionManager

__all__ = [
    "Checkpoint",
    "CheckpointStore",
    "FileCheckpointStore",
    "InMemoryCheckpointStore",
    "SessionManager",
]
