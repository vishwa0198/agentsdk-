"""agentsdk/messages.py

Foundation message and memory layer for the agent SDK.
Imported by every other module — types are strict, frozen where immutable,
and fully compatible with Pydantic v2.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 1. Message roles
# ---------------------------------------------------------------------------


class MessageRole(str, Enum):
    """Conversation roles that map directly to LLM API role fields."""

    system = "system"
    human = "human"
    ai = "ai"
    tool_result = "tool_result"


# ---------------------------------------------------------------------------
# 2. Tool call
# ---------------------------------------------------------------------------


class ToolCall(BaseModel):
    """A tool invocation the AI has requested."""

    model_config = ConfigDict(frozen=True)

    id: str
    """Unique call identifier, e.g. ``call_abc123``."""

    name: str
    """Name of the tool to invoke."""

    arguments: dict[str, Any]
    """Parsed JSON arguments for the tool."""


# ---------------------------------------------------------------------------
# 3. Message types
# ---------------------------------------------------------------------------

# Role → API name (OpenAI-compatible; provider layer adapts for Anthropic).
_ROLE_TO_API: dict[MessageRole, str] = {
    MessageRole.system: "system",
    MessageRole.human: "user",
    MessageRole.ai: "assistant",
    MessageRole.tool_result: "tool",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BaseMessage(BaseModel):
    """Shared fields for every message in a conversation."""

    model_config = ConfigDict(frozen=True)

    role: MessageRole
    content: str
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to an API-compatible dict (OpenAI / Anthropic base shape)."""
        return {"role": _ROLE_TO_API[self.role], "content": self.content}


class SystemMessage(BaseMessage):
    """A system-prompt message; role is always ``system``."""

    role: Literal[MessageRole.system] = MessageRole.system


class HumanMessage(BaseMessage):
    """A user-turn message; role is always ``human`` (maps to ``user`` in APIs)."""

    role: Literal[MessageRole.human] = MessageRole.human


class AIMessage(BaseMessage):
    """An assistant-turn message; role is always ``ai`` (maps to ``assistant`` in APIs)."""

    role: Literal[MessageRole.ai] = MessageRole.ai
    tool_calls: list[ToolCall] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        # OpenAI expects a JSON string, not a dict
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in self.tool_calls
            ]
        return d


class ToolResultMessage(BaseMessage):
    """The result of a tool invocation; role is always ``tool_result``."""

    role: Literal[MessageRole.tool_result] = MessageRole.tool_result
    tool_call_id: str
    is_error: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["tool_call_id"] = self.tool_call_id
        return d


# ---------------------------------------------------------------------------
# 4. MessageHistory
# ---------------------------------------------------------------------------


class MessageHistory:
    """Stateful, mutable container for a conversation's messages.

    Provides shorthand constructors (add_system, add_human, add_ai,
    add_tool_result) and serialization to OpenAI-compatible dict lists.

    Example::

        history = MessageHistory()
        history.add_system("You are a helpful assistant.")
        history.add_human("What is 2 + 2?")
        print(history.to_dict_list())
    """

    def __init__(self) -> None:
        self._messages: list[BaseMessage] = []

    # ------------------------------------------------------------------
    # Core mutation
    # ------------------------------------------------------------------

    def add(self, message: BaseMessage) -> None:
        """Append *message* to the history."""
        self._messages.append(message)

    # ------------------------------------------------------------------
    # Shorthand constructors
    # ------------------------------------------------------------------

    def add_system(self, content: str) -> None:
        """Append a :class:`SystemMessage`."""
        self.add(SystemMessage(content=content))

    def add_human(self, content: str) -> None:
        """Append a :class:`HumanMessage`."""
        self.add(HumanMessage(content=content))

    def add_ai(
        self,
        content: str,
        tool_calls: list[ToolCall] | None = None,
    ) -> None:
        """Append an :class:`AIMessage`, optionally with tool calls."""
        self.add(AIMessage(content=content, tool_calls=tool_calls or []))

    def add_tool_result(
        self,
        tool_call_id: str,
        content: str,
        is_error: bool = False,
    ) -> None:
        """Append a :class:`ToolResultMessage`."""
        self.add(
            ToolResultMessage(
                content=content,
                tool_call_id=tool_call_id,
                is_error=is_error,
            )
        )

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_all(self) -> list[BaseMessage]:
        """Return a shallow copy of the full message list."""
        return list(self._messages)

    def last(self, n: int = 1) -> list[BaseMessage]:
        """Return the last *n* messages (fewer if history is shorter)."""
        if n <= 0:
            return []
        return self._messages[-n:]

    def clear(self) -> None:
        """Remove all messages from the history."""
        self._messages.clear()

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict_list(self) -> list[dict[str, Any]]:
        """Serialize every message to its API-compatible dict representation.

        The output shape is OpenAI-compatible (role names ``user`` /
        ``assistant`` / ``system`` / ``tool``) so the provider abstraction
        layer can forward it with zero transformation.
        """
        return [m.to_dict() for m in self._messages]

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def token_estimate(self) -> int:
        """Rough token count: ``sum(words * 1.3)`` across all messages."""
        return round(sum(len(m.content.split()) * 1.3 for m in self._messages))

    def __len__(self) -> int:
        return len(self._messages)

    def __repr__(self) -> str:  # pragma: no cover
        return f"MessageHistory(messages={len(self._messages)})"


# ---------------------------------------------------------------------------
# 5. Memory protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Memory(Protocol):
    """Async persistence interface for conversation histories.

    Phase 4 (persistence) will provide concrete implementations backed by
    Redis, a database, or the file system.  The agent loop type-hints against
    this protocol so any conforming object is accepted without coupling to a
    specific backend.
    """

    async def load(self, session_id: str) -> MessageHistory:
        """Load (or create) the :class:`MessageHistory` for *session_id*."""
        ...

    async def save(self, session_id: str, history: MessageHistory) -> None:
        """Persist *history* under *session_id*."""
        ...


