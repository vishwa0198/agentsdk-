"""Coding Agent — agentsdk demonstration project.

Creates a fully configured agent that writes, tests, and saves Python
solutions using the ReAct (Reason + Act) loop.

Usage::

    from coding_agent.agent import create_coding_agent
    agent = create_coding_agent()
    result = await agent.run("Write a Sieve of Eratosthenes", session_id="s1")
    print(result.output)
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from agentsdk import Agent, AgentConfig, GroqProvider
from agentsdk.memory.rag_memory import RAGMemory
from agentsdk.memory.vector_store import VectorMemoryStore
from agentsdk.persistence.file_store import FileCheckpointStore
from agentsdk.persistence.session import SessionManager
from agentsdk.tools.builtin import read_file, run_python, set_default_store, write_file
from agentsdk.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert Python coding agent. When given a task:
1. Think through the solution step by step
2. Write clean, well-commented Python code
3. Use run_python to test your code immediately
4. If it fails, read the error, fix the code, and retry
5. Once working, use write_file to save the final solution
6. Report what the code does and show the output

Always test before saving. Never save broken code."""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_coding_agent() -> Agent:
    """Build and return a fully configured CodingAgent.

    Loads ``GROQ_API_KEY`` from the ``.env`` file, overriding any stale
    environment variable already set in the shell.

    Components created:

    * **RAGMemory** backed by a persistent ChromaDB collection
      ``"coding-agent"`` — enables semantic retrieval of past solutions.
    * **FileCheckpointStore + SessionManager** — persists full conversation
      history as JSON so sessions can be resumed with ``--session``.
    * **ToolRegistry** containing ``run_python``, ``write_file``,
      and ``read_file``.

    Returns
    -------
    Agent
        Ready-to-use agent. Call ``await agent.run(task, session_id=sid)``
        to start a coding task.
    """
    load_dotenv(override=True)

    # ── Memory: semantic retrieval across sessions ─────────────────────────
    store = VectorMemoryStore(collection_name="coding-agent")
    set_default_store(store)  # wires ingest_document if added later
    memory = RAGMemory(store=store, max_messages=20)

    # ── Persistence: deterministic JSON checkpoints ────────────────────────
    checkpoint_store = FileCheckpointStore()
    session_manager = SessionManager(store=checkpoint_store, agent_name="CodingAgent")

    # ── Tools ─────────────────────────────────────────────────────────────
    registry = ToolRegistry()
    registry.register_many([run_python, write_file, read_file])

    # ── LLM ───────────────────────────────────────────────────────────────
    llm = GroqProvider(api_key=os.environ["GROQ_API_KEY"])

    config = AgentConfig(
        name="CodingAgent",
        system_prompt=SYSTEM_PROMPT,
        max_iterations=15,
        verbose=True,
    )

    return Agent(
        config=config,
        llm=llm,
        memory=memory,
        registry=registry,
        session_manager=session_manager,
    )
