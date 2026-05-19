"""tests/test_smoke.py

Smoke test suite for agentsdk.
All tests use a MockLLMProvider — zero real API calls required.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Shared mock LLM
# ---------------------------------------------------------------------------


class MockLLMProvider:
    """Returns a fixed end_turn response — no network calls."""

    async def complete(self, history, tools=None, max_tokens=1024):
        from agentsdk.messages import AIMessage
        from agentsdk.llm import LLMResponse

        return LLMResponse(
            message=AIMessage(content="Mock response."),
            model="mock-groq",
            input_tokens=10,
            output_tokens=5,
            stop_reason="end_turn",
        )


# ---------------------------------------------------------------------------
# Test 1 — Agent.run() returns AgentResult with correct output
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_run_returns_mock_response():
    from agentsdk.agent import Agent, AgentConfig

    config = AgentConfig(name="TestAgent", system_prompt="You are helpful.")
    agent = Agent(config=config, llm=MockLLMProvider())
    result = await agent.run("Hello")

    assert result.output == "Mock response."
    assert result.stopped_by == "end_turn"
    assert len(result.steps) == 1


# ---------------------------------------------------------------------------
# Test 2 — @tool decorator builds correct ToolSchema from type hints
# ---------------------------------------------------------------------------


def test_tool_decorator_builds_schema():
    from agentsdk.tools.base import tool

    @tool
    async def add_numbers(a: int, b: int) -> str:
        """Add two integers and return the result."""
        return str(a + b)

    schema = add_numbers.schema
    assert schema.name == "add_numbers"
    assert schema.description == "Add two integers and return the result."
    assert schema.parameters["properties"]["a"] == {"type": "integer"}
    assert schema.parameters["properties"]["b"] == {"type": "integer"}
    assert set(schema.parameters["required"]) == {"a", "b"}


# ---------------------------------------------------------------------------
# Test 3 — ToolRegistry.register() raises ValueError on duplicate name
# ---------------------------------------------------------------------------


def test_tool_registry_raises_on_duplicate():
    from agentsdk.tools.base import tool
    from agentsdk.tools.registry import ToolRegistry

    @tool
    async def my_tool(x: str) -> str:
        """A test tool."""
        return x

    registry = ToolRegistry()
    registry.register(my_tool)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(my_tool)


# ---------------------------------------------------------------------------
# Test 4 — MessageHistory.to_dict_list() returns correct role/content dicts
# ---------------------------------------------------------------------------


def test_message_history_to_dict_list():
    from agentsdk.messages import MessageHistory

    history = MessageHistory()
    history.add_system("You are helpful.")
    history.add_human("Hello")
    history.add_ai("Hi there!")

    dicts = history.to_dict_list()

    assert dicts[0] == {"role": "system", "content": "You are helpful."}
    assert dicts[1] == {"role": "user", "content": "Hello"}
    assert dicts[2] == {"role": "assistant", "content": "Hi there!"}


# ---------------------------------------------------------------------------
# Test 5 — SessionManager saves and loads history via InMemoryCheckpointStore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_manager_save_and_load():
    from agentsdk.messages import MessageHistory
    from agentsdk.persistence.checkpoint import InMemoryCheckpointStore
    from agentsdk.persistence.session import SessionManager

    store = InMemoryCheckpointStore()
    manager = SessionManager(store=store, agent_name="TestAgent")

    history = MessageHistory()
    history.add_system("You are helpful.")
    history.add_human("Hello")
    history.add_ai("Hi there!")

    await manager.save_history("session-1", history)
    loaded = await manager.load_history("session-1")

    dicts = loaded.to_dict_list()
    assert len(dicts) == 3
    assert dicts[0]["role"] == "system"
    assert dicts[1]["role"] == "user"
    assert dicts[2]["role"] == "assistant"


# ---------------------------------------------------------------------------
# Test 6 — AgentGraph._topological_sort() raises ValueError on cycle
# ---------------------------------------------------------------------------


def test_agent_graph_detects_cycle():
    from agentsdk.agent import Agent, AgentConfig
    from agentsdk.graph.graph import AgentGraph
    from agentsdk.graph.node import AgentNode, Edge

    config = AgentConfig(name="A", system_prompt="")
    llm = MockLLMProvider()

    a = AgentNode(node_id="a", agent=Agent(config=config, llm=llm))
    b = AgentNode(node_id="b", agent=Agent(config=config, llm=llm))

    graph = AgentGraph()
    graph.add_node(a)
    graph.add_node(b)
    graph.add_edge(Edge(from_node="a", to_node="b"))
    graph.add_edge(Edge(from_node="b", to_node="a"))  # creates a cycle
    graph.set_entry("a")
    graph.set_exit("b")

    with pytest.raises(ValueError, match="[Cc]ycle"):
        graph._topological_sort()


# ---------------------------------------------------------------------------
# Test 7 — Agent.run() with tool use: tool_use on iter 1, end_turn on iter 2
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_with_tool_use():
    from agentsdk.agent import Agent, AgentConfig
    from agentsdk.messages import AIMessage, ToolCall
    from agentsdk.llm import LLMResponse
    from agentsdk.tools.base import tool

    call_count = 0

    class MockLLMWithToolCall:
        async def complete(self, history, tools=None, max_tokens=1024):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    message=AIMessage(
                        content="I'll add those numbers.",
                        tool_calls=[
                            ToolCall(id="call_1", name="add", arguments={"a": 2, "b": 3})
                        ],
                    ),
                    model="mock-groq",
                    input_tokens=10,
                    output_tokens=5,
                    stop_reason="tool_use",
                )
            return LLMResponse(
                message=AIMessage(content="The result is 5."),
                model="mock-groq",
                input_tokens=10,
                output_tokens=5,
                stop_reason="end_turn",
            )

    @tool
    async def add(a: int, b: int) -> str:
        """Add two integers."""
        return str(a + b)

    config = AgentConfig(name="TestAgent", system_prompt="You are helpful.")
    agent = Agent(config=config, llm=MockLLMWithToolCall(), tools=[add])
    result = await agent.run("What is 2 + 3?")

    assert result.output == "The result is 5."
    assert result.stopped_by == "end_turn"
    assert call_count == 2
    assert len(result.steps) == 2
