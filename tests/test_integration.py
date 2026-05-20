"""tests/test_integration.py

Integration tests against the real Groq API.

Run with:
    pytest tests/test_integration.py -v -m integration

Skipped automatically when GROQ_API_KEY is not set.
"""

from __future__ import annotations

import os

import pytest

groq_key = os.environ.get("GROQ_API_KEY")
pytestmark = pytest.mark.skipif(not groq_key, reason="GROQ_API_KEY not set")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent(system_prompt: str, tools=None, registry=None):
    from agentsdk import Agent, AgentConfig, GroqProvider

    return Agent(
        config=AgentConfig(
            name="IntegrationAgent",
            system_prompt=system_prompt,
            max_iterations=5,
        ),
        llm=GroqProvider(api_key=groq_key),
        tools=tools,
        registry=registry,
    )


# ---------------------------------------------------------------------------
# Test 1 — basic reasoning, no tools
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_basic_agent_run():
    agent = _agent("You are a helpful assistant. Answer concisely.")
    result = await agent.run("What is 2 + 2?")
    assert "4" in result.output
    assert result.stopped_by == "end_turn"


# ---------------------------------------------------------------------------
# Test 2 — get_datetime tool
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_with_get_datetime_tool():
    import datetime

    from agentsdk.tools.builtin import get_datetime

    year = str(datetime.datetime.now().year)
    agent = _agent("Use tools when asked.", tools=[get_datetime])
    result = await agent.run("What is the current year?")
    assert year in result.output


# ---------------------------------------------------------------------------
# Test 3 — run_python tool (unsafe mode — no Docker required in CI)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_with_run_python_tool():
    from agentsdk.tools.builtin import run_python

    os.environ["AGENTSDK_UNSAFE_PYTHON"] = "1"
    try:
        agent = _agent(
            "Use run_python to execute code when asked.",
            tools=[run_python],
        )
        result = await agent.run(
            "Use run_python to compute sum(range(10)) and report the result."
        )
        assert "45" in result.output
    finally:
        os.environ.pop("AGENTSDK_UNSAFE_PYTHON", None)


# ---------------------------------------------------------------------------
# Test 4 — write then read a file
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_with_write_and_read_file():
    from agentsdk.tools.builtin import read_file, write_file

    test_path = "/tmp/agentsdk_integration_test.txt"
    agent = _agent(
        "Use write_file and read_file tools exactly as instructed.",
        tools=[write_file, read_file],
    )
    result = await agent.run(
        f"Write the text 'hello agentsdk' to {test_path}, "
        f"then read it back and confirm its contents."
    )
    assert "hello agentsdk" in result.output.lower() or "hello" in result.output.lower()


# ---------------------------------------------------------------------------
# Test 5 — multi-turn session recalls earlier information
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_turn_session():
    from agentsdk import FileCheckpointStore, SessionManager
    from agentsdk.persistence.checkpoint import InMemoryCheckpointStore

    store = InMemoryCheckpointStore()
    session_mgr = SessionManager(store=store, agent_name="IntegrationAgent")

    from agentsdk import Agent, AgentConfig, GroqProvider

    agent = Agent(
        config=AgentConfig(
            name="IntegrationAgent",
            system_prompt="You are a helpful assistant with memory.",
            max_iterations=3,
        ),
        llm=GroqProvider(api_key=groq_key),
        session_manager=session_mgr,
    )

    sid = "integration-session-multi-turn"
    await agent.run("Remember this: my lucky number is 42.", session_id=sid)
    result = await agent.run("What is my lucky number?", session_id=sid)
    assert "42" in result.output


# ---------------------------------------------------------------------------
# Test 6 — two-node AgentGraph
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_graph_two_nodes():
    from agentsdk import Agent, AgentConfig, AgentGraph, AgentNode, Edge, GroqProvider
    from agentsdk.graph.runner import GraphRunner

    llm = GroqProvider(api_key=groq_key)

    researcher = Agent(
        config=AgentConfig(
            name="Researcher",
            system_prompt="Summarise the topic in 3 bullet points.",
            max_iterations=2,
        ),
        llm=llm,
    )
    summariser = Agent(
        config=AgentConfig(
            name="Summariser",
            system_prompt="Turn the bullet points into one sentence.",
            max_iterations=2,
        ),
        llm=llm,
    )

    graph = AgentGraph()
    graph.add_node(AgentNode(node_id="researcher", agent=researcher))
    graph.add_node(AgentNode(node_id="summariser", agent=summariser))
    graph.add_edge(
        Edge(from_node="researcher", to_node="summariser", data_map={"output": "input"})
    )
    graph.set_entry("researcher")
    graph.set_exit("summariser")

    result = await GraphRunner(graph).run({"input": "Python async/await"})
    assert isinstance(result.get("output"), str)
    assert len(result["output"]) > 0


# ---------------------------------------------------------------------------
# Test 7 — parallel tool calls (datetime + run_python simultaneously)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parallel_tool_calls():
    import datetime

    from agentsdk.tools.builtin import get_datetime, run_python

    os.environ["AGENTSDK_UNSAFE_PYTHON"] = "1"
    try:
        year = str(datetime.datetime.now().year)
        agent = _agent(
            "Use the available tools to answer questions. "
            "You may call multiple tools in the same turn.",
            tools=[get_datetime, run_python],
        )
        result = await agent.run(
            "Get the current datetime AND use run_python to compute 6 * 7. "
            "Report both results."
        )
        # Both results must appear in the output
        assert "42" in result.output
        assert result.stopped_by == "end_turn"
        # Verify both tools were actually called
        called = [tc.name for step in result.steps for tc in step.tool_calls]
        assert "get_datetime" in called
        assert "run_python" in called
    finally:
        os.environ.pop("AGENTSDK_UNSAFE_PYTHON", None)


# ---------------------------------------------------------------------------
# Test 8 — RetryableLLMProvider retries on mock rate-limit errors
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retry_on_mock_rate_limit():
    from agentsdk.exceptions import LLMRateLimitError
    from agentsdk.llm import LLMResponse, RetryConfig, RetryableLLMProvider
    from agentsdk.messages import AIMessage, MessageHistory

    call_count = 0

    class MockRateLimitProvider:
        async def complete(self, history, tools=None, max_tokens=1024):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise LLMRateLimitError("mock rate limit")
            return LLMResponse(
                message=AIMessage(content="Success after retries."),
                model="mock",
                input_tokens=5,
                output_tokens=5,
                stop_reason="end_turn",
            )

    provider = RetryableLLMProvider(
        provider=MockRateLimitProvider(),
        config=RetryConfig(max_retries=3, base_delay=0.01, max_delay=0.1),
    )

    history = MessageHistory()
    history.add_human("Hello")
    result = await provider.complete(history)

    assert result.message.content == "Success after retries."
    assert call_count == 3  # 2 failures + 1 success
