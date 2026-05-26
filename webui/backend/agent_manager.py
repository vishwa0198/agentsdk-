"""webui/backend/agent_manager.py

Manages Agent instances — one per session, shared store per agent_name.
Handles creation, session listing, and deletion.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv, find_dotenv

from agentsdk import Agent, AgentConfig, OllamaProvider
from agentsdk.memory.rag_memory import RAGMemory
from agentsdk.memory.vector_store import VectorMemoryStore
from agentsdk.persistence.checkpoint import Checkpoint
from agentsdk.persistence.file_store import FileCheckpointStore
from agentsdk.persistence.session import SessionManager
from agentsdk.tools.builtin import (
    get_datetime,
    http_request,
    read_file,
    run_python,
    write_file,
)
from agentsdk.tools.registry import ToolRegistry
from agentsdk.mcp.client import MCPTool

from models import SessionInfo

# Tool registry shared across all WebAgent instances.
# Excludes ingest_document to avoid global-store contention across sessions.
_WEB_TOOLS = ToolRegistry()
_WEB_TOOLS.register_many([http_request, read_file, write_file, run_python, get_datetime])


class AgentManager:
    """Singleton that owns all Agent instances for the web UI.

    One Agent is created per ``session_id`` on first use and cached for the
    lifetime of the process.  A single :class:`FileCheckpointStore` is shared
    across all sessions (files are namespaced by agent_name/session_id).
    """

    def __init__(self) -> None:
        # find_dotenv searches upward from cwd to locate .env (e.g. at repo root).
        load_dotenv(find_dotenv(usecwd=True), override=True)
        # Ensure run_python uses the local subprocess fallback during dev.
        # Can be explicitly disabled by setting AGENTSDK_UNSAFE_PYTHON=0.
        if os.environ.get("AGENTSDK_UNSAFE_PYTHON", "1") != "0":
            os.environ["AGENTSDK_UNSAFE_PYTHON"] = "1"
        self._agents: dict[str, Agent] = {}
        self._stores: dict[str, VectorMemoryStore] = {}
        self._checkpoint_store = FileCheckpointStore()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_create(self, session_id: str, agent_name: str = "WebAgent", system_prompt: str | None = None) -> Agent:
        """Return the cached Agent for *session_id*, or build a new one.

        Each session gets its own ChromaDB collection (named after
        ``session_id``) so vector data never leaks between sessions.
        """
        if session_id in self._agents:
            return self._agents[session_id]

        # ChromaDB collection names must match [a-zA-Z0-9._-] and be 3-512 chars.
        # Replace colons (used for user-namespacing) with double underscores.
        chroma_name = session_id.replace(":", "__")
        # ── per-session vector store ──────────────────────────────────────
        store = VectorMemoryStore(collection_name=chroma_name)
        memory = RAGMemory(store=store, max_messages=20)

        # ── persistence ───────────────────────────────────────────────────
        session_manager = SessionManager(
            store=self._checkpoint_store,
            agent_name=agent_name,
        )

        # ── LLM ───────────────────────────────────────────────────────────
        # Model from env; defaults to llama3:8b (available locally via Ollama).
        model = os.environ.get("OLLAMA_MODEL", "llama3:8b")
        llm = OllamaProvider(model=model)

        config = AgentConfig(
            name=agent_name,
            system_prompt=system_prompt or (
                "You are a helpful AI assistant with access to tools. "
                "Use them when needed. For simple factual questions, answer directly."
            ),
            max_iterations=10,
            max_tokens=2048,
            max_history_messages=8,
            verbose=True,
        )

        agent = Agent(
            config=config,
            llm=llm,
            memory=memory,
            registry=_WEB_TOOLS,
            session_manager=session_manager,
        )

        self._agents[session_id] = agent
        self._stores[session_id] = store
        return agent

    async def list_sessions(self, agent_name: str) -> list[SessionInfo]:
        """Return metadata for all persisted sessions of *agent_name*."""
        session_ids = await self._checkpoint_store.list_sessions(agent_name)
        result: list[SessionInfo] = []

        for sid in session_ids:
            cp: Checkpoint | None = await self._checkpoint_store.load(sid)
            if cp is None:
                continue
            result.append(
                SessionInfo(
                    session_id=cp.session_id,
                    agent_name=cp.agent_name,
                    message_count=len(cp.history),
                    updated_at=cp.updated_at.isoformat(),
                )
            )

        # Most recently updated first.
        result.sort(key=lambda s: s.updated_at, reverse=True)
        return result

    async def delete_session(self, session_id: str) -> None:
        """Delete the checkpoint file and ChromaDB collection for *session_id*."""
        # Remove JSON checkpoint.
        await self._checkpoint_store.delete(session_id)

        # Remove ChromaDB collection (entire collection, not just documents).
        if session_id in self._stores:
            store = self._stores.pop(session_id)
            try:
                store._client.delete_collection(session_id)
            except Exception:
                # Fallback: delete all documents if collection drop fails.
                await store.delete_session(session_id)

        # Evict cached Agent so a new session_id can be reused cleanly.
        self._agents.pop(session_id, None)

    def sync_mcp_tools(self, session_id: str, mcp_tools: list[MCPTool]) -> None:
        """Replace all MCPTool entries in the agent's tool list with the current set.

        Called before every ``agent.run()`` in the WebSocket handler so the
        agent always sees the latest set of connected MCP tools.
        """
        if session_id not in self._agents:
            return
        agent = self._agents[session_id]
        # Keep all non-MCP tools (built-ins); replace MCP tools wholesale.
        non_mcp = [t for t in agent._tools if not isinstance(t, MCPTool)]
        agent._tools = non_mcp + list(mcp_tools)
        agent._tool_map = {t.schema.name: t for t in agent._tools}
