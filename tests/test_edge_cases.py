"""tests/test_edge_cases.py

Edge case tests for agentsdk.
All tests use local mock LLM providers — zero real API calls.
"""

from __future__ import annotations

import pytest

from agentsdk.agent import Agent, AgentConfig
from agentsdk.graph.graph import AgentGraph
from agentsdk.graph.node import AgentNode, Edge
from agentsdk.graph.runner import GraphRunner
from agentsdk.llm import LLMResponse
from agentsdk.messages import AIMessage, MessageHistory, ToolCall, ToolResultMessage
from agentsdk.persistence.checkpoint import InMemoryCheckpointStore
from agentsdk.persistence.session import SessionManager
from agentsdk.tools.base import tool
from agentsdk.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class _EndTurnLLM:
    """Always returns a fixed end_turn response."""

    def __init__(self, content: str = "Done.") -> None:
        self._content = content

    async def complete(self, history, tools=None, max_tokens=1024):
        return LLMResponse(
            message=AIMessage(content=self._content),
            model="mock",
            input_tokens=10,
            output_tokens=5,
            stop_reason="end_turn",
        )


def _make_agent(llm=None, tools=None, max_iterations: int = 10) -> Agent:
    config = AgentConfig(
        name="TestAgent",
        system_prompt="You are helpful.",
        max_iterations=max_iterations,
    )
    return Agent(config=config, llm=llm or _EndTurnLLM(), tools=tools or [])


# ---------------------------------------------------------------------------
# Test 1 — Empty tool result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_empty_tool_result():
    """Tool returning empty string must not crash; ToolResultMessage.content == ''."""

    @tool
    async def empty_tool(x: str) -> str:
        """Returns an empty string."""
        return ""

    call_count = 0
    captured: dict = {}

    class _LLM:
        async def complete(self, history, tools=None, max_tokens=1024):
            nonlocal call_count
            call_count += 1
            captured["history"] = history
            if call_count == 1:
                return LLMResponse(
                    message=AIMessage(
                        content="calling empty tool",
                        tool_calls=[ToolCall(id="c1", name="empty_tool", arguments={"x": "hi"})],
                    ),
                    model="mock",
                    input_tokens=10,
                    output_tokens=5,
                    stop_reason="tool_use",
                )
            return LLMResponse(
                message=AIMessage(content="Done."),
                model="mock",
                input_tokens=10,
                output_tokens=5,
                stop_reason="end_turn",
            )

    agent = _make_agent(llm=_LLM(), tools=[empty_tool])
    result = await agent.run("test empty")

    assert result.stopped_by == "end_turn"
    assert result.output == "Done."

    tool_results = [
        m for m in captured["history"].get_all() if isinstance(m, ToolResultMessage)
    ]
    assert len(tool_results) == 1
    assert tool_results[0].content == ""
    assert tool_results[0].is_error is False


# ---------------------------------------------------------------------------
# Test 2 — Max iterations hit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_max_iterations_hit():
    """LLM that never returns end_turn must be stopped at max_iterations."""

    class _AlwaysToolCallLLM:
        async def complete(self, history, tools=None, max_tokens=1024):
            return LLMResponse(
                message=AIMessage(
                    content="looping",
                    tool_calls=[ToolCall(id="loop", name="no_such_tool", arguments={})],
                ),
                model="mock",
                input_tokens=5,
                output_tokens=3,
                stop_reason="tool_use",
            )

    agent = _make_agent(llm=_AlwaysToolCallLLM(), max_iterations=3)
    result = await agent.run("loop forever")

    assert result.stopped_by == "max_iterations"
    assert len(result.steps) == 3


# ---------------------------------------------------------------------------
# Test 3 — Tool raises exception → is_error=True, agent continues
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_tool_raises_exception():
    """Raised exception in tool must set is_error=True; agent must recover."""

    @tool
    async def broken_tool(x: str) -> str:
        """Always raises."""
        raise ValueError("something broke")

    call_count = 0
    captured: dict = {}

    class _LLM:
        async def complete(self, history, tools=None, max_tokens=1024):
            nonlocal call_count
            call_count += 1
            captured["history"] = history
            if call_count == 1:
                return LLMResponse(
                    message=AIMessage(
                        content="calling broken",
                        tool_calls=[ToolCall(id="c_err", name="broken_tool", arguments={"x": "test"})],
                    ),
                    model="mock",
                    input_tokens=10,
                    output_tokens=5,
                    stop_reason="tool_use",
                )
            return LLMResponse(
                message=AIMessage(content="Recovered."),
                model="mock",
                input_tokens=10,
                output_tokens=5,
                stop_reason="end_turn",
            )

    agent = _make_agent(llm=_LLM(), tools=[broken_tool])
    result = await agent.run("test broken")

    assert result.stopped_by == "end_turn"
    assert result.output == "Recovered."

    tool_results = [
        m for m in captured["history"].get_all() if isinstance(m, ToolResultMessage)
    ]
    assert len(tool_results) == 1
    assert tool_results[0].is_error is True
    assert "something broke" in tool_results[0].content


# ---------------------------------------------------------------------------
# Test 4 — Unknown tool called by LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_unknown_tool_called_by_llm():
    """LLM requesting a nonexistent tool must get is_error=True result, not raise."""

    call_count = 0
    captured: dict = {}

    class _LLM:
        async def complete(self, history, tools=None, max_tokens=1024):
            nonlocal call_count
            call_count += 1
            captured["history"] = history
            if call_count == 1:
                return LLMResponse(
                    message=AIMessage(
                        content="calling nonexistent",
                        tool_calls=[ToolCall(id="cx", name="nonexistent_tool", arguments={})],
                    ),
                    model="mock",
                    input_tokens=10,
                    output_tokens=5,
                    stop_reason="tool_use",
                )
            return LLMResponse(
                message=AIMessage(content="Done."),
                model="mock",
                input_tokens=10,
                output_tokens=5,
                stop_reason="end_turn",
            )

    agent = _make_agent(llm=_LLM())
    result = await agent.run("call a nonexistent tool")

    assert result.stopped_by == "end_turn"

    tool_results = [
        m for m in captured["history"].get_all() if isinstance(m, ToolResultMessage)
    ]
    assert len(tool_results) == 1
    assert tool_results[0].is_error is True
    assert tool_results[0].content == "Tool not found: nonexistent_tool"


# ---------------------------------------------------------------------------
# Test 5 — Empty user input
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_empty_user_input():
    """agent.run('') must complete without error and produce non-empty output."""
    agent = _make_agent()
    result = await agent.run("")

    assert result.output != ""
    assert result.stopped_by == "end_turn"


# ---------------------------------------------------------------------------
# Test 6 — Very long user input
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_very_long_user_input():
    """agent.run with a 10,000-char input must complete; token estimate > 0."""
    agent = _make_agent()
    result = await agent.run("x" * 10_000)

    assert result.output != ""
    assert result.total_input_tokens > 0


# ---------------------------------------------------------------------------
# Test 7 — Tool returning None is converted to string "None"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_tool_with_none_return():
    """FunctionTool.execute() must convert None return to the string 'None'."""

    @tool
    async def none_tool() -> str:
        """Returns nothing."""
        return None  # type: ignore[return-value]

    result = await none_tool.execute()

    assert isinstance(result, str)
    assert result == "None"


# ---------------------------------------------------------------------------
# Test 8 — MessageHistory.token_estimate() on empty history
# ---------------------------------------------------------------------------


@pytest.mark.edge
def test_message_history_token_estimate_empty():
    """token_estimate() on an empty MessageHistory must return 0, not raise."""
    history = MessageHistory()

    assert history.token_estimate() == 0


# ---------------------------------------------------------------------------
# Test 9 — Session fork preserves history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_session_fork_preserves_history():
    """Forked session must contain identical history length and content."""
    store = InMemoryCheckpointStore()
    manager = SessionManager(store=store, agent_name="TestAgent")

    history = MessageHistory()
    history.add_system("You are helpful.")
    history.add_human("Hello")
    history.add_ai("Hi there!")

    await manager.save_history("session-original", history)
    await manager.fork("session-original", "session-fork")

    original = await manager.load_history("session-original")
    forked = await manager.load_history("session-fork")

    assert len(original) == len(forked) == 3
    for orig_d, fork_d in zip(original.to_dict_list(), forked.to_dict_list()):
        assert orig_d["role"] == fork_d["role"]
        assert orig_d["content"] == fork_d["content"]


# ---------------------------------------------------------------------------
# Test 10 — Graph with a single node (no edges)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_graph_single_node():
    """A single-node graph with no edges must run and return that node's output."""
    agent = _make_agent(llm=_EndTurnLLM("Single node output."))
    node = AgentNode(node_id="solo", agent=agent)

    graph = AgentGraph()
    graph.add_node(node)
    graph.set_entry("solo")
    graph.set_exit("solo")

    runner = GraphRunner(graph)
    output = await runner.run({"input": "Hello"})

    assert output["output"] == "Single node output."


# ---------------------------------------------------------------------------
# Test 11 — Graph with no entry node raises ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_graph_missing_entry_raises():
    """GraphRunner.run() must raise ValueError when no entry node is set."""
    agent = _make_agent()
    graph = AgentGraph()
    graph.add_node(AgentNode(node_id="orphan", agent=agent))
    # Intentionally omit graph.set_entry() and graph.set_exit()

    runner = GraphRunner(graph)
    with pytest.raises(ValueError, match="no entry node"):
        await runner.run({"input": "Hi"})


# ---------------------------------------------------------------------------
# Test 12 — Parallel tool calls all errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_parallel_tool_calls_all_errors():
    """Three simultaneous tool calls that all raise must each produce is_error=True."""

    @tool
    async def fail_a() -> str:
        """Always fails."""
        raise RuntimeError("error A")

    @tool
    async def fail_b() -> str:
        """Always fails."""
        raise RuntimeError("error B")

    @tool
    async def fail_c() -> str:
        """Always fails."""
        raise RuntimeError("error C")

    call_count = 0
    captured: dict = {}

    class _LLM:
        async def complete(self, history, tools=None, max_tokens=1024):
            nonlocal call_count
            call_count += 1
            captured["history"] = history
            if call_count == 1:
                return LLMResponse(
                    message=AIMessage(
                        content="calling all three failing tools",
                        tool_calls=[
                            ToolCall(id="ca", name="fail_a", arguments={}),
                            ToolCall(id="cb", name="fail_b", arguments={}),
                            ToolCall(id="cc", name="fail_c", arguments={}),
                        ],
                    ),
                    model="mock",
                    input_tokens=10,
                    output_tokens=5,
                    stop_reason="tool_use",
                )
            return LLMResponse(
                message=AIMessage(content="All tools failed but I recovered."),
                model="mock",
                input_tokens=10,
                output_tokens=5,
                stop_reason="end_turn",
            )

    agent = _make_agent(llm=_LLM(), tools=[fail_a, fail_b, fail_c])
    result = await agent.run("test parallel errors")

    assert result.stopped_by == "end_turn"
    assert result.output == "All tools failed but I recovered."

    tool_results = [
        m for m in captured["history"].get_all() if isinstance(m, ToolResultMessage)
    ]
    assert len(tool_results) == 3
    assert all(tr.is_error for tr in tool_results)
