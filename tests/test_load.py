"""tests/test_load.py

Load and performance tests for agentsdk.
All tests use MockLLMProvider — zero real API calls.
"""

from __future__ import annotations

import asyncio
import time
import tracemalloc

import pytest

from agentsdk.agent import Agent, AgentConfig
from agentsdk.llm import LLMResponse, ToolSchema
from agentsdk.messages import AIMessage, MessageHistory
from agentsdk.persistence.checkpoint import InMemoryCheckpointStore
from agentsdk.persistence.session import SessionManager
from agentsdk.tools.base import FunctionTool
from agentsdk.tools.registry import ToolRegistry


class MockLLMProvider:
    """Returns a fixed end_turn response — no network calls."""

    async def complete(self, history, tools=None, max_tokens=1024):
        return LLMResponse(
            message=AIMessage(content="Mock response."),
            model="mock",
            input_tokens=10,
            output_tokens=5,
            stop_reason="end_turn",
        )


# ---------------------------------------------------------------------------
# Test 1 — 20 concurrent agent runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.load
async def test_concurrent_agent_runs():
    """20 agents launched concurrently must all complete successfully."""
    config = AgentConfig(name="LoadAgent", system_prompt="You are helpful.")

    async def _run_one() -> str:
        agent = Agent(config=config, llm=MockLLMProvider())
        result = await agent.run("test")
        return result.output

    start = time.monotonic()
    results = await asyncio.gather(*[_run_one() for _ in range(20)])
    elapsed = time.monotonic() - start

    assert all(r == "Mock response." for r in results), "Not all agents returned expected output"
    print(f"\n20 agents in {elapsed:.2f}s")


# ---------------------------------------------------------------------------
# Test 2 — MessageHistory with 1000 messages serialises in under 1 second
# ---------------------------------------------------------------------------


@pytest.mark.load
def test_message_history_large():
    """Building 1000-message history and calling to_dict_list() must complete < 1s."""
    history = MessageHistory()
    for i in range(500):
        history.add_human(f"Human message {i}")
        history.add_ai(f"AI response {i}")

    assert len(history) == 1000

    start = time.monotonic()
    result = history.to_dict_list()
    elapsed = time.monotonic() - start

    assert len(result) == 1000
    assert elapsed < 1.0, f"to_dict_list() took {elapsed:.3f}s — expected < 1s"


# ---------------------------------------------------------------------------
# Test 3 — ToolRegistry lookup speed
# ---------------------------------------------------------------------------


@pytest.mark.load
def test_tool_registry_lookup_speed():
    """10,000 name lookups across a 100-tool registry must complete in under 0.5s."""
    registry = ToolRegistry()

    # Register 100 uniquely-named tools using FunctionTool directly.
    for i in range(100):
        async def _noop(x: str = "") -> str:
            return x

        ft = FunctionTool(
            fn=_noop,
            tool_schema=ToolSchema(
                name=f"tool_{i}",
                description=f"Tool number {i}.",
                parameters={"type": "object", "properties": {}, "required": []},
            ),
        )
        registry.register(ft)

    start = time.monotonic()
    for j in range(10_000):
        name = f"tool_{j % 100}"
        found = registry.get(name)
        assert found is not None
    elapsed = time.monotonic() - start

    assert elapsed < 0.5, f"10,000 lookups took {elapsed:.3f}s — expected < 0.5s"


# ---------------------------------------------------------------------------
# Test 4 — SessionManager handles 50 sessions correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.load
async def test_session_manager_many_sessions():
    """50 sessions with 10 messages each must save and reload correctly in < 2s."""
    store = InMemoryCheckpointStore()
    manager = SessionManager(store=store, agent_name="LoadAgent")

    start = time.monotonic()

    for i in range(50):
        history = MessageHistory()
        for j in range(5):
            history.add_human(f"human {j}")
            history.add_ai(f"ai {j}")
        await manager.save_history(f"session-{i}", history)

    loaded = []
    for i in range(50):
        h = await manager.load_history(f"session-{i}")
        loaded.append(h)

    elapsed = time.monotonic() - start

    assert all(len(h) == 10 for h in loaded), "Some sessions did not load 10 messages"
    assert elapsed < 2.0, f"50 sessions took {elapsed:.3f}s — expected < 2s"


# ---------------------------------------------------------------------------
# Test 5 — Memory usage for 500-message history stays under 50 MB
# ---------------------------------------------------------------------------


@pytest.mark.load
def test_memory_usage_large_history():
    """Building 500 HumanMessage + 500 AIMessage must use less than 50 MB peak."""
    tracemalloc.start()

    history = MessageHistory()
    for i in range(500):
        history.add_human(f"Human message {i} with realistic content for sizing.")
        history.add_ai(f"AI response {i} that is a bit longer to simulate real output.")

    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mb = peak / (1024 * 1024)
    assert peak_mb < 50.0, f"Peak memory {peak_mb:.1f} MB exceeded 50 MB"
