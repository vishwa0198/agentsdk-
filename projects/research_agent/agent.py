"""Research Agent — agentsdk demonstration project.

Creates a fully configured research agent that fetches web pages, ingests
them into vector memory, and synthesises structured Markdown reports.

Usage::

    from research_agent.agent import create_research_agent
    agent = create_research_agent()
    result = await agent.run("The history of Python", session_id="s1")
    print(result.output)
"""

from __future__ import annotations

import os
import re

import httpx
from dotenv import load_dotenv

from agentsdk import Agent, AgentConfig, OllamaProvider
from agentsdk.memory.rag_memory import RAGMemory
from agentsdk.memory.vector_store import VectorMemoryStore
from agentsdk.messages import HumanMessage
from agentsdk.persistence.file_store import FileCheckpointStore
from agentsdk.persistence.session import SessionManager
from agentsdk.tools.base import tool
from agentsdk.tools.builtin import (
    get_datetime,
    http_request,
    ingest_document,
    read_file,
    set_default_store,
    write_file,
)
from agentsdk.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Module-level store reference — set by create_research_agent()
# ---------------------------------------------------------------------------

_research_store: VectorMemoryStore | None = None

# ---------------------------------------------------------------------------
# Custom tool: fetch_and_ingest
# ---------------------------------------------------------------------------


@tool
async def fetch_and_ingest(url: str, session_id: str) -> str:
    """Fetch a web page and ingest its text content into vector memory.

    Strips HTML tags, normalises whitespace, splits the text into 500-character
    overlapping chunks, and stores each chunk as a :class:`HumanMessage` in the
    configured vector store under *session_id*.

    Args:
        url: The web page URL to fetch.
        session_id: Session identifier used to namespace the stored chunks.

    Returns:
        A summary string such as ``"Fetched and ingested 4821 chars from https://…"``,
        or an error string if the fetch or store is unavailable.
    """
    if _research_store is None:
        return "Error: no store configured. Call create_research_agent() first."

    # ── Fetch ──────────────────────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (research-agent/1.0)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text
    except httpx.HTTPStatusError as exc:
        return f"Error fetching {url}: HTTP {exc.response.status_code}"
    except Exception as exc:  # noqa: BLE001
        return f"Error fetching {url}: {exc}"

    # ── Strip HTML ─────────────────────────────────────────────────────────
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z]{2,6};", " ", text)
    text = re.sub(r"&#?\w+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return f"Error: no text content extracted from {url}"

    # ── Chunk (500 chars, 50-char overlap) and store ───────────────────────
    chunk_size, overlap = 500, 50
    step = chunk_size - overlap
    chunks = [
        text[i : i + chunk_size]
        for i in range(0, len(text), step)
        if text[i : i + chunk_size].strip()
    ]

    for idx, chunk in enumerate(chunks):
        msg = HumanMessage(
            content=chunk,
            metadata={"source": url, "chunk": idx},
        )
        await _research_store.add(session_id, msg)

    return f"Fetched and ingested {len(text)} chars from {url}"


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a research agent. When given a topic:
1. Use http_request to fetch relevant web pages (start with Wikipedia or authoritative sources)
2. Use ingest_document to store fetched content into memory for later retrieval
3. Gather information from at least 3 different sources
4. Synthesise findings into a structured report with sections:
   - Summary (2-3 sentences)
   - Key Facts (bullet points)
   - Details (2-3 paragraphs)
   - Sources (URLs used)
5. Use write_file to save the report as a .md file in /tmp/research/

Always cite your sources. Never make up facts."""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_research_agent() -> Agent:
    """Build and return a fully configured ResearchAgent.

    Requires Ollama to be running locally (``ollama serve``).

    Components created:

    * **RAGMemory** backed by a persistent ChromaDB collection
      ``"research-agent"`` — enables semantic retrieval of ingested web content.
    * **FileCheckpointStore + SessionManager** — persists conversation history
      as JSON so sessions can be resumed with ``--session``.
    * **ToolRegistry** containing ``http_request``, ``fetch_and_ingest``,
      ``ingest_document``, ``write_file``, ``read_file``, ``get_datetime``.

    The module-level ``_research_store`` is wired up here so that the
    :func:`fetch_and_ingest` tool can access the store at call time.

    Returns
    -------
    Agent
        Ready-to-use agent. Call ``await agent.run(topic, session_id=sid)``
        to start a research task.
    """
    global _research_store
    load_dotenv(override=True)

    # ── Memory: semantic retrieval of ingested web content ────────────────
    store = VectorMemoryStore(collection_name="research-agent")
    _research_store = store       # wire fetch_and_ingest
    set_default_store(store)      # wire ingest_document

    memory = RAGMemory(store=store, max_messages=30)

    # ── Persistence: deterministic JSON checkpoints ────────────────────────
    checkpoint_store = FileCheckpointStore()
    session_manager = SessionManager(store=checkpoint_store, agent_name="ResearchAgent")

    # ── Tools ─────────────────────────────────────────────────────────────
    registry = ToolRegistry()
    registry.register_many(
        [
            http_request,
            fetch_and_ingest,
            ingest_document,
            write_file,
            read_file,
            get_datetime,
        ]
    )

    # ── LLM ───────────────────────────────────────────────────────────────
    llm = OllamaProvider()

    config = AgentConfig(
        name="ResearchAgent",
        system_prompt=SYSTEM_PROMPT,
        max_iterations=20,
        verbose=True,
    )

    return Agent(
        config=config,
        llm=llm,
        memory=memory,
        registry=registry,
        session_manager=session_manager,
    )
