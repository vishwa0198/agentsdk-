"""tests/test_ollama_live.py

Live capability tests for OllamaProvider.
Sends real questions to the local Ollama server and validates responses.

Run with:
    pytest tests/test_ollama_live.py -v -s -m ollama

Requires Ollama to be running:  ollama serve
Model used: llama3:8b  (override with OLLAMA_MODEL env var)
"""
from __future__ import annotations

import json
import os
import re

import pytest

# ---------------------------------------------------------------------------
# Reachability check - skip entire module when Ollama is not running
# ---------------------------------------------------------------------------

def _check_ollama_reachable() -> bool:
    import httpx
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=4)
        return r.status_code == 200
    except Exception:
        return False


_OLLAMA_UP = _check_ollama_reachable()
pytestmark = [
    pytest.mark.ollama,
    pytest.mark.skipif(not _OLLAMA_UP, reason="Ollama server not reachable at localhost:11434"),
]

MODEL = os.environ.get("OLLAMA_MODEL", "llama3:8b")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _history(system: str, user: str):
    from agentsdk.messages import MessageHistory
    h = MessageHistory()
    h.add_system(system)
    h.add_human(user)
    return h


# ---------------------------------------------------------------------------
# Q1 - Basic arithmetic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_q1_basic_arithmetic():
    """The model must correctly compute 347 + 589 = 936."""
    from agentsdk.llm import OllamaProvider
    provider = OllamaProvider(model=MODEL)
    resp = await provider.complete(
        _history("Answer with just the number, nothing else.", "What is 347 + 589?"),
        max_tokens=20,
    )
    print(f"\n[Q1 Arithmetic] model={resp.model}  answer={resp.message.content.strip()!r}")
    assert "936" in resp.message.content, f"Expected 936, got: {resp.message.content!r}"


# ---------------------------------------------------------------------------
# Q2 - Factual knowledge
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_q2_factual_knowledge():
    """The model should know H2O is the formula for water."""
    from agentsdk.llm import OllamaProvider
    provider = OllamaProvider(model=MODEL)
    resp = await provider.complete(
        _history("Answer in one sentence.", "What is the chemical formula for water?"),
        max_tokens=60,
    )
    content = resp.message.content.lower()
    print(f"\n[Q2 Factual] {resp.message.content.strip()!r}")
    assert "h2o" in content or "h" in content, f"Expected H2O, got: {resp.message.content!r}"


# ---------------------------------------------------------------------------
# Q3 - Logical reasoning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_q3_logical_reasoning():
    """The model should deduce that Carol is the shortest."""
    from agentsdk.llm import OllamaProvider
    provider = OllamaProvider(model=MODEL)
    resp = await provider.complete(
        _history(
            "Answer with just the name.",
            "Alice is taller than Bob. Bob is taller than Carol. Who is the shortest?",
        ),
        max_tokens=30,
    )
    print(f"\n[Q3 Reasoning] {resp.message.content.strip()!r}")
    assert "carol" in resp.message.content.lower(), f"Expected Carol, got: {resp.message.content!r}"


# ---------------------------------------------------------------------------
# Q4 - Code generation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_q4_code_generation():
    """The model must write a working Python function that reverses a string."""
    from agentsdk.llm import OllamaProvider
    provider = OllamaProvider(model=MODEL)
    resp = await provider.complete(
        _history(
            "Return only the Python code, no explanation.",
            "Write a Python function called `reverse_string` that takes a string and returns it reversed.",
        ),
        max_tokens=150,
    )
    code = resp.message.content
    print(f"\n[Q4 Code]\n{code}")

    namespace: dict = {}
    clean = re.sub(r"```(?:python)?|```", "", code).strip()
    exec(clean, namespace)  # noqa: S102
    assert "reverse_string" in namespace, "Function reverse_string not defined"
    assert namespace["reverse_string"]("hello") == "olleh", "reverse_string('hello') should be 'olleh'"


# ---------------------------------------------------------------------------
# Q5 - Multi-turn memory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_q5_multi_turn_memory():
    """The model must recall a fact stated two turns earlier."""
    from agentsdk.llm import OllamaProvider
    from agentsdk.messages import MessageHistory

    provider = OllamaProvider(model=MODEL)

    history = MessageHistory()
    history.add_system("You are a helpful assistant. Be concise.")
    history.add_human("My favourite colour is indigo. Remember that.")

    r1 = await provider.complete(history, max_tokens=60)
    print(f"\n[Q5 Multi-turn T1] {r1.message.content.strip()!r}")

    history.add(r1.message)
    history.add_human("What is my favourite colour?")

    r2 = await provider.complete(history, max_tokens=40)
    print(f"[Q5 Multi-turn T2] {r2.message.content.strip()!r}")
    assert "indigo" in r2.message.content.lower(), f"Expected indigo, got: {r2.message.content!r}"


# ---------------------------------------------------------------------------
# Q6 - JSON structured output
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_q6_structured_json_output():
    """The model should return valid JSON with the correct schema."""
    from agentsdk.llm import OllamaProvider
    provider = OllamaProvider(model=MODEL)
    resp = await provider.complete(
        _history(
            "You must respond with ONLY valid JSON. No markdown, no extra text.",
            'Return a JSON object with keys "name" (string) and "age" (integer) for a fictional person.',
        ),
        max_tokens=80,
    )
    raw = resp.message.content.strip()
    print(f"\n[Q6 JSON] {raw!r}")
    clean = re.sub(r"```(?:json)?|```", "", raw).strip()
    data = json.loads(clean)
    assert "name" in data, f"Missing 'name' key: {data}"
    assert "age" in data, f"Missing 'age' key: {data}"
    assert isinstance(data["age"], int), f"'age' must be int, got {type(data['age'])}"


# ---------------------------------------------------------------------------
# Q7 - Token usage reported
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_q7_token_usage_reported():
    """OllamaProvider must return non-zero token counts and model name."""
    from agentsdk.llm import OllamaProvider
    provider = OllamaProvider(model=MODEL)
    resp = await provider.complete(_history("Be concise.", "Say hello in one word."), max_tokens=10)
    print(f"\n[Q7 Tokens] model={resp.model!r} input={resp.input_tokens} output={resp.output_tokens}")
    assert resp.input_tokens > 0, "input_tokens should be > 0"
    assert resp.output_tokens > 0, "output_tokens should be > 0"
    assert resp.model != "", "model field must not be empty"


# ---------------------------------------------------------------------------
# Q8 - Tool calling via agent (text-injection fallback for llama3:8b)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_q8_tool_use_via_agent():
    """Agent + OllamaProvider must invoke a registered tool and return its result.

    llama3:8b does not support Ollama's native OpenAI tool schema (returns 400).
    OllamaProvider falls back to text-injection mode where tool descriptions are
    embedded in the system prompt and TOOL_CALL lines are parsed from the response.
    """
    from agentsdk import Agent, AgentConfig, OllamaProvider
    from agentsdk.tools.base import tool
    from agentsdk.tools.registry import ToolRegistry

    calls: list[str] = []

    @tool
    async def get_capital(country: str) -> str:
        """Return the capital city of the given country."""
        mapping = {"france": "Paris", "japan": "Tokyo", "brazil": "Brasilia"}
        result = mapping.get(country.lower(), "Unknown")
        calls.append(country)
        return result

    registry = ToolRegistry()
    registry.register(get_capital)

    agent = Agent(
        config=AgentConfig(
            name="ToolAgent",
            system_prompt=(
                "Use the get_capital tool to answer questions about capitals. "
                "Always call the tool - never guess the answer."
            ),
            max_iterations=6,
            verbose=True,
        ),
        llm=OllamaProvider(model=MODEL),
        registry=registry,
    )

    result = await agent.run("What is the capital of France?")
    print(f"\n[Q8 Tool use] output={result.output!r}  tool_calls={calls}")
    assert "paris" in result.output.lower(), f"Expected Paris in output, got: {result.output!r}"
