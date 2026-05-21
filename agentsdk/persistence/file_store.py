"""agentsdk/persistence/file_store.py

JSON file-backed CheckpointStore implementation.
"""

from __future__ import annotations

import json
from pathlib import Path

import aiofiles

from agentsdk.persistence.checkpoint import Checkpoint


class FileCheckpointStore:
    """Stores each checkpoint as a JSON file on disk.

    Layout::

        {base_dir}/{agent_name}/{session_id}.json

    The directory is created on first save.

    Args:
        base_dir: Root directory for all checkpoints.
            Default ``".agentsdk/checkpoints"``.

    Example::

        store = FileCheckpointStore(base_dir=".agentsdk/checkpoints")
        manager = SessionManager(store=store, agent_name="MyAgent")
    """

    def __init__(self, base_dir: str = ".agentsdk/checkpoints") -> None:
        self._base = Path(base_dir)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _path(self, agent_name: str, session_id: str) -> Path:
        return self._base / agent_name / f"{session_id}.json"

    def _find(self, session_id: str) -> Path | None:
        """Search across all agent subdirectories for *session_id*."""
        matches = list(self._base.glob(f"*/{session_id}.json"))
        return matches[0] if matches else None

    # ------------------------------------------------------------------
    # CheckpointStore interface
    # ------------------------------------------------------------------

    async def save(self, checkpoint: Checkpoint) -> None:
        path = self._path(checkpoint.agent_name, checkpoint.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(checkpoint.model_dump(mode="json"), indent=2))

    async def load(self, session_id: str) -> Checkpoint | None:
        path = self._find(session_id)
        if path is None:
            return None
        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                data = json.loads(await f.read())
            return Checkpoint.model_validate(data)
        except Exception:  # noqa: BLE001 — corrupted/missing files return None
            return None

    async def delete(self, session_id: str) -> None:
        path = self._find(session_id)
        if path is not None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    async def list_sessions(self, agent_name: str | None = None) -> list[str]:
        if not self._base.exists():
            return []
        if agent_name is not None:
            pattern = f"{agent_name}/*.json"
        else:
            pattern = "**/*.json"
        return [p.stem for p in self._base.glob(pattern)]
