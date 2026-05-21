"""tests/test_error_scenarios.py

Error scenario and graceful-degradation tests for agentsdk.
Uses unittest.mock.patch to simulate failures — zero real API calls.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from agentsdk.exceptions import (
    GraphExecutionError,
    LLMAuthError,
    LLMProviderError,
    LLMRateLimitError,
)
from agentsdk.llm import (
    CircuitBreaker,
    LLMResponse,
    RetryConfig,
    RetryableLLMProvider,
)
from agentsdk.messages import AIMessage, MessageHistory
from agentsdk.persistence.file_store import FileCheckpointStore


class _MockLLM:
    """Simple end-turn mock — used wherever a working LLM is needed."""

    async def complete(self, history, tools=None, max_tokens=1024):
        return LLMResponse(
            message=AIMessage(content="Mock response."),
            model="mock",
            input_tokens=10,
            output_tokens=5,
            stop_reason="end_turn",
        )


# ---------------------------------------------------------------------------
# Test 1 — LLMAuthError propagates out of agent.run()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_llm_auth_error_raises():
    """agent.run() must propagate LLMAuthError — never swallow it."""
    from agentsdk.agent import Agent, AgentConfig

    class _AuthFailLLM:
        async def complete(self, history, tools=None, max_tokens=1024):
            raise LLMAuthError("invalid API key")

    config = AgentConfig(name="TestAgent", system_prompt="You are helpful.")
    agent = Agent(config=config, llm=_AuthFailLLM())

    with pytest.raises(LLMAuthError):
        await agent.run("test")


# ---------------------------------------------------------------------------
# Test 2 — RetryableLLMProvider retries on LLMRateLimitError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_llm_rate_limit_with_retry():
    """RetryableLLMProvider must retry twice then return the success response."""
    call_count = 0

    class _RateLimitThenSucceedLLM:
        async def complete(self, history, tools=None, max_tokens=1024):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise LLMRateLimitError("rate limited")
            return LLMResponse(
                message=AIMessage(content="Success after retry."),
                model="mock",
                input_tokens=10,
                output_tokens=5,
                stop_reason="end_turn",
            )

    retryable = RetryableLLMProvider(
        provider=_RateLimitThenSucceedLLM(),
        config=RetryConfig(max_retries=3, base_delay=0.0),
    )

    result = await retryable.complete(MessageHistory())

    assert result.message.content == "Success after retry."
    assert call_count == 3


# ---------------------------------------------------------------------------
# Test 3 — CircuitBreaker opens after threshold failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_circuit_breaker_opens():
    """CircuitBreaker must open after threshold failures; 4th call raises LLMProviderError."""
    cb = CircuitBreaker(threshold=3)

    for _ in range(3):
        cb.record_failure()

    assert cb.is_open() is True

    # Inject the open circuit into a RetryableLLMProvider and verify it rejects calls.
    inner = MagicMock()
    retryable = RetryableLLMProvider(
        provider=inner,
        config=RetryConfig(circuit_breaker_threshold=3),
    )
    retryable._circuit = cb  # inject the already-open breaker

    with pytest.raises(LLMProviderError, match="Circuit breaker"):
        await retryable.complete(MessageHistory())

    # The underlying provider must never have been called.
    inner.complete.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4 — CircuitBreaker recovers after timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_circuit_breaker_recovers():
    """Circuit breaker must transition OPEN → HALF_OPEN → CLOSED after timeout + success."""
    cb = CircuitBreaker(threshold=1, timeout=60.0)

    with patch("agentsdk.llm.time") as mock_time:
        mock_time.monotonic.return_value = 0.0
        cb.record_failure()
        assert cb.is_open() is True  # OPEN

        mock_time.monotonic.return_value = 61.0  # advance past timeout
        assert cb.is_open() is False  # transitions to HALF_OPEN

    # Make a successful call through the breaker (now in HALF_OPEN state).
    retryable = RetryableLLMProvider(
        provider=_MockLLM(),
        config=RetryConfig(),
    )
    retryable._circuit = cb

    result = await retryable.complete(MessageHistory())
    assert result.message.content == "Mock response."

    # After success the circuit must be CLOSED — is_open() returns False.
    assert cb.is_open() is False


# ---------------------------------------------------------------------------
# Test 5 — FileCheckpointStore.load() returns None on corrupted JSON
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_file_checkpoint_store_corrupted_file():
    """load() must return None gracefully when the file contains invalid JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = FileCheckpointStore(base_dir=tmpdir)

        # Write invalid JSON where the checkpoint would be found by _find().
        agent_dir = os.path.join(tmpdir, "TestAgent")
        os.makedirs(agent_dir, exist_ok=True)
        corrupt_path = os.path.join(agent_dir, "corrupted-session.json")
        with open(corrupt_path, "w") as f:
            f.write("this is not valid JSON {{{")

        result = await store.load("corrupted-session")

    assert result is None


# ---------------------------------------------------------------------------
# Test 6 — run_python tool times out correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_run_python_timeout():
    """run_python with an infinite-sleep script must return timeout error within ~12s."""
    from agentsdk.tools.builtin import run_python

    with patch.dict(os.environ, {"AGENTSDK_UNSAFE_PYTHON": "1"}):
        result = await run_python.execute(code="import time; time.sleep(30)")

    assert result == "Error: timeout after 10s"


# ---------------------------------------------------------------------------
# Test 7 — http_request to a refused port returns Error string, not exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_http_request_connection_refused():
    """http_request to a closed port must return an 'Error: ...' string, not raise."""
    from agentsdk.tools.builtin import http_request

    # Port 19999 is chosen to be almost certainly unused.
    result = await http_request.execute(
        url="http://localhost:19999", method="GET", body=""
    )

    assert result.startswith("Error:")


# ---------------------------------------------------------------------------
# Test 8 — GraphRunner propagates node failure as GraphExecutionError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.edge
async def test_graph_node_failure_propagates():
    """A failing first node must cause GraphRunner to raise GraphExecutionError."""
    from agentsdk.agent import Agent, AgentConfig
    from agentsdk.graph.graph import AgentGraph
    from agentsdk.graph.node import AgentNode, Edge
    from agentsdk.graph.runner import GraphRunner

    class _FailingLLM:
        async def complete(self, history, tools=None, max_tokens=1024):
            raise RuntimeError("node agent crashed")

    config = AgentConfig(name="FailAgent", system_prompt="fail")
    failing_agent = Agent(config=config, llm=_FailingLLM())
    passing_agent = Agent(config=config, llm=_MockLLM())

    graph = AgentGraph()
    graph.add_node(AgentNode(node_id="node_a", agent=failing_agent))
    graph.add_node(AgentNode(node_id="node_b", agent=passing_agent))
    graph.add_edge(Edge(from_node="node_a", to_node="node_b"))
    graph.set_entry("node_a")
    graph.set_exit("node_b")

    runner = GraphRunner(graph)

    with pytest.raises(GraphExecutionError) as exc_info:
        await runner.run({"input": "start"})

    assert "node_a" in str(exc_info.value)
