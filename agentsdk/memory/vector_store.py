"""agentsdk/memory/vector_store.py

ChromaDB-backed vector store for semantic message retrieval.

Requires the ``rag`` optional extras::

    pip install agentsdk-py[rag]
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from agentsdk.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    MessageRole,
    SystemMessage,
    ToolResultMessage,
)
from agentsdk.memory.embedder import Embedder, LocalEmbedder

if TYPE_CHECKING:
    import chromadb as _chromadb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc_id(session_id: str, message: BaseMessage) -> str:
    """Stable, URL-safe document ID derived from session + message identity."""
    raw = f"{session_id}:{message.created_at.isoformat()}:{message.content[:80]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _reconstruct(content: str, meta: dict[str, Any]) -> BaseMessage:
    """Re-hydrate a :class:`BaseMessage` subclass from ChromaDB metadata."""
    role = meta.get("role", MessageRole.human.value)
    created_at = datetime.fromisoformat(meta["created_at"])

    if role == MessageRole.system.value:
        return SystemMessage(content=content, created_at=created_at)
    if role == MessageRole.ai.value:
        return AIMessage(content=content, created_at=created_at)
    if role == MessageRole.tool_result.value:
        return ToolResultMessage(
            content=content,
            created_at=created_at,
            tool_call_id=meta.get("tool_call_id", "unknown"),
        )
    # default: human
    return HumanMessage(content=content, created_at=created_at)


# ---------------------------------------------------------------------------
# VectorMemoryStore
# ---------------------------------------------------------------------------


class VectorMemoryStore:
    """Persistent vector store backed by ChromaDB.

    Each :class:`~agentsdk.messages.BaseMessage` is embedded and stored as a
    ChromaDB document with ``session_id``/``role``/``created_at`` metadata,
    enabling both semantic search and chronological retrieval.

    Args:
        collection_name: Name of the ChromaDB collection to use or create.
        persist_dir: Directory where ChromaDB writes its on-disk files.
            Defaults to ``.agentsdk/chroma`` relative to the working directory.
        embedder: Embedding backend.  Defaults to
            :class:`~agentsdk.memory.embedder.LocalEmbedder`.

    Raises:
        ImportError: If ``chromadb`` is not installed.
    """

    def __init__(
        self,
        collection_name: str,
        persist_dir: str = ".agentsdk/chroma",
        embedder: Embedder | None = None,
    ) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise ImportError(
                "chromadb is required for VectorMemoryStore. "
                "Install it with: pip install agentsdk-py[rag]"
            ) from exc

        self._embedder: Embedder = embedder or LocalEmbedder()
        self._client: _chromadb.PersistentClient = chromadb.PersistentClient(
            path=persist_dir
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            # Use cosine distance for sentence-transformer vectors.
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        """Run the (blocking) embedder in a thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._embedder.embed, texts)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def add(self, session_id: str, message: BaseMessage) -> None:
        """Embed and store *message* under *session_id*.

        Silently skips empty-content messages to avoid ChromaDB errors.

        Args:
            session_id: Logical session identifier.
            message: Message to persist.
        """
        if not message.content.strip():
            return

        doc_id = _make_doc_id(session_id, message)
        embeddings = await self._embed([message.content])

        meta: dict[str, Any] = {
            "session_id": session_id,
            "role": message.role.value,
            "created_at": message.created_at.isoformat(),
        }
        # Preserve tool_call_id for ToolResultMessage reconstruction.
        if isinstance(message, ToolResultMessage):
            meta["tool_call_id"] = message.tool_call_id

        self._collection.upsert(
            ids=[doc_id],
            embeddings=embeddings,
            documents=[message.content],
            metadatas=[meta],
        )

    async def search(
        self,
        session_id: str,
        query: str,
        n_results: int = 5,
    ) -> list[BaseMessage]:
        """Semantic search over messages for *session_id*.

        Args:
            session_id: Filter results to this session.
            query: Natural-language search query.
            n_results: Maximum number of results to return.

        Returns:
            Matching messages sorted by ``created_at`` (oldest first).
        """
        # Guard: ChromaDB raises if n_results > collection size.
        count = self._collection.count()
        if count == 0:
            return []
        n_results = min(n_results, count)

        embeddings = await self._embed([query])
        results = self._collection.query(
            query_embeddings=embeddings,
            n_results=n_results,
            where={"session_id": session_id},
            include=["documents", "metadatas"],
        )

        messages: list[BaseMessage] = []
        docs = results.get("documents") or [[]]
        metas = results.get("metadatas") or [[]]
        for doc, meta in zip(docs[0], metas[0]):
            messages.append(_reconstruct(doc, meta))

        return sorted(messages, key=lambda m: m.created_at)

    async def get_all(self, session_id: str) -> list[BaseMessage]:
        """Retrieve every message stored under *session_id*.

        Args:
            session_id: Session to query.

        Returns:
            All messages sorted by ``created_at`` (oldest first).
        """
        results = self._collection.get(
            where={"session_id": session_id},
            include=["documents", "metadatas"],
        )

        messages: list[BaseMessage] = []
        for doc, meta in zip(
            results.get("documents") or [],
            results.get("metadatas") or [],
        ):
            messages.append(_reconstruct(doc, meta))

        return sorted(messages, key=lambda m: m.created_at)

    async def delete_session(self, session_id: str) -> None:
        """Remove all documents belonging to *session_id*.

        Args:
            session_id: Session whose data should be purged.
        """
        results = self._collection.get(
            where={"session_id": session_id},
            include=[],  # IDs only — no need to fetch documents.
        )
        ids = results.get("ids") or []
        if ids:
            self._collection.delete(ids=ids)
