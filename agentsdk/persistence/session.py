"""agentsdk/persistence/session.py

SessionManager — high-level interface that Agent talks to for persistence.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from agentsdk.messages import (
    AIMessage,
    HumanMessage,
    MessageHistory,
    SystemMessage,
    ToolCall,
    ToolResultMessage,
)
from agentsdk.persistence.checkpoint import Checkpoint, CheckpointStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _history_from_dict_list(dict_list: list[dict]) -> MessageHistory:
    """Reconstruct a MessageHistory from an OpenAI-format dict list.

    This reverses MessageHistory.to_dict_list().  Fields lost during
    serialisation (``created_at``, ``metadata``, ``is_error``) receive
    their defaults on reconstruction.
    """
    history = MessageHistory()
    for d in dict_list:
        role = d.get("role", "")
        content = d.get("content", "")

        if role == "system":
            history.add(SystemMessage(content=content))

        elif role == "user":
            history.add(HumanMessage(content=content))

        elif role == "assistant":
            raw_tcs = d.get("tool_calls") or []
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=json.loads(tc["function"]["arguments"]),
                )
                for tc in raw_tcs
            ]
            history.add(AIMessage(content=content, tool_calls=tool_calls))

        elif role == "tool":
            history.add(
                ToolResultMessage(
                    tool_call_id=d["tool_call_id"],
                    content=content,
                    # is_error is not persisted in to_dict(); default to False.
                    is_error=False,
                )
            )
        # Unknown roles are silently skipped.

    return history


class SessionManager:
    """High-level session interface wrapping a CheckpointStore.

    One SessionManager is scoped to a single agent (agent_name).
    Multiple agents can share the same underlying store safely.

    Args:
        store: Any CheckpointStore implementation (InMemoryCheckpointStore
            or FileCheckpointStore).
        agent_name: Name scoping this manager to a specific agent.

    Example::

        store = FileCheckpointStore(base_dir=".agentsdk/checkpoints")
        manager = SessionManager(store=store, agent_name="MyAgent")
        agent = Agent(config=config, llm=llm, session_manager=manager)
    """

    def __init__(self, store: CheckpointStore, agent_name: str) -> None:
        self._store = store
        self._agent_name = agent_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def load_history(self, session_id: str) -> MessageHistory:
        """Load the message history for *session_id*.

        Returns an empty ``MessageHistory`` when no checkpoint exists.
        """
        checkpoint = await self._store.load(session_id)
        if checkpoint is None:
            return MessageHistory()
        return _history_from_dict_list(checkpoint.history)

    async def save_history(
        self,
        session_id: str,
        history: MessageHistory,
        iteration: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> Checkpoint:
        """Persist *history* for *session_id* and return the saved Checkpoint.

        Increments ``version`` each call.  Preserves ``created_at`` from the
        first save so the session's original timestamp is stable.
        """
        if metadata is None:
            metadata = {}

        existing = await self._store.load(session_id)
        version = (existing.version + 1) if existing is not None else 1
        created_at = existing.created_at if existing is not None else _utcnow()

        checkpoint = Checkpoint(
            session_id=session_id,
            agent_name=self._agent_name,
            history=history.to_dict_list(),
            iteration=iteration,
            metadata=metadata,
            created_at=created_at,
            updated_at=_utcnow(),
            version=version,
        )
        await self._store.save(checkpoint)
        return checkpoint

    async def fork(
        self, source_session_id: str, new_session_id: str
    ) -> Checkpoint | None:
        """Branch *source_session_id* into a new independent session.

        Copies the full history and iteration count, resets ``version`` to 1
        and stamps a fresh ``created_at``.  Returns ``None`` when the source
        session doesn't exist.
        """
        source = await self._store.load(source_session_id)
        if source is None:
            return None

        now = _utcnow()
        forked = Checkpoint(
            session_id=new_session_id,
            agent_name=source.agent_name,
            history=list(source.history),
            iteration=source.iteration,
            metadata=dict(source.metadata),
            created_at=now,
            updated_at=now,
            version=1,
        )
        await self._store.save(forked)
        return forked

    async def list_sessions(self) -> list[str]:
        """Return all session IDs belonging to this agent."""
        return await self._store.list_sessions(agent_name=self._agent_name)
