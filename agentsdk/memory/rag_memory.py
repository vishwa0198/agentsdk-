"""agentsdk/memory/rag_memory.py

RAG-powered :class:`~agentsdk.messages.Memory` implementation.

Instead of returning the raw full history (which may exceed the LLM's context
window), :class:`RAGMemory` applies a **recency + relevance** strategy:

1. Always include the system message (if any).
2. Always keep the last *N* messages for conversational coherence.
3. Fill remaining slots with semantically relevant messages retrieved via the
   :class:`~agentsdk.memory.vector_store.VectorMemoryStore`.
4. Deduplicate and sort chronologically before returning.
"""

from __future__ import annotations

from agentsdk.messages import (
    HumanMessage,
    MessageHistory,
    SystemMessage,
)
from agentsdk.memory.vector_store import VectorMemoryStore

# How many recent messages always survive the recency window.
_RECENCY_TAIL = 5


class RAGMemory:
    """Recency + relevance memory backed by a :class:`VectorMemoryStore`.

    Implements the :class:`~agentsdk.messages.Memory` protocol so it can be
    passed directly to :class:`~agentsdk.agent.Agent`.

    Args:
        store: The vector store used for persistence and retrieval.
        max_messages: Maximum number of messages to include in the loaded
            :class:`~agentsdk.messages.MessageHistory`.  When the stored
            history is shorter, all messages are returned unchanged.
        semantic_k: Number of additional messages fetched via semantic search
            to supplement the recency tail.
    """

    def __init__(
        self,
        store: VectorMemoryStore,
        max_messages: int = 20,
        semantic_k: int = 5,
    ) -> None:
        self._store = store
        self._max_messages = max_messages
        self._semantic_k = semantic_k
        # Tracks doc IDs already in the store to avoid duplicate upserts.
        self._stored_keys: set[str] = set()

    # ------------------------------------------------------------------
    # Memory protocol
    # ------------------------------------------------------------------

    async def load(self, session_id: str) -> MessageHistory:
        """Load (and optionally truncate) the conversation for *session_id*.

        When the total stored messages exceed :attr:`max_messages` the
        returned history is assembled from:

        * The **system message** (keeps agent persona intact).
        * The **last 5 messages** (conversational recency).
        * Up to ``semantic_k`` messages retrieved by semantic similarity to
          the most recent human message (retrieval-augmented relevance).

        Args:
            session_id: Conversation identifier.

        Returns:
            A :class:`~agentsdk.messages.MessageHistory` ready for the agent.
        """
        all_msgs = await self._store.get_all(session_id)

        # Fast-path: history fits within the window — return as-is.
        if len(all_msgs) <= self._max_messages:
            history = MessageHistory()
            for msg in all_msgs:
                history.add(msg)
            return history

        # --- Recency + relevance selection ---

        system_msgs = [m for m in all_msgs if isinstance(m, SystemMessage)]
        recency_tail = all_msgs[-_RECENCY_TAIL:]

        # Use the most recent human message as the semantic query.
        last_human = next(
            (m for m in reversed(all_msgs) if isinstance(m, HumanMessage)),
            None,
        )
        semantic_hits: list = []
        if last_human:
            semantic_hits = await self._store.search(
                session_id, last_human.content, n_results=self._semantic_k
            )

        # Deduplicate by (created_at, first-20-chars) key — preserves order.
        seen: set[str] = set()
        combined = []
        for msg in system_msgs + recency_tail + semantic_hits:
            key = f"{msg.created_at.isoformat()}:{msg.content[:20]}"
            if key not in seen:
                seen.add(key)
                combined.append(msg)

        # Sort chronologically, then honour the hard message cap.
        combined.sort(key=lambda m: m.created_at)
        combined = combined[: self._max_messages]

        history = MessageHistory()
        for msg in combined:
            history.add(msg)
        return history

    async def save(self, session_id: str, history: MessageHistory) -> None:
        """Persist new messages from *history* into the vector store.

        Messages already persisted (tracked by an in-process set) are skipped
        to avoid duplicate embeddings.

        Args:
            session_id: Conversation identifier.
            history: Full conversation history to persist.
        """
        for msg in history.get_all():
            key = f"{session_id}:{msg.created_at.isoformat()}:{msg.content[:40]}"
            if key not in self._stored_keys:
                await self._store.add(session_id, msg)
                self._stored_keys.add(key)
