"""agentsdk/llm.py

LLM provider abstraction — Ollama backend with a swappable Protocol interface.

Import chain:
    agent loop → LLMProvider (Protocol)
                  └── OllamaProvider (concrete, local Ollama server)

Provider-specific quirks stay fully inside each provider class.
The agent loop only ever calls ``LLMProvider.complete()``.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import uuid
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from agentsdk.exceptions import LLMAuthError, LLMProviderError, LLMRateLimitError
from agentsdk.messages import AIMessage, MessageHistory, ToolCall


# ---------------------------------------------------------------------------
# Tool schema — provider-agnostic tool definition
# ---------------------------------------------------------------------------


class ToolSchema(BaseModel):
    """A tool definition passed to the LLM alongside the message history."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    parameters: dict[str, Any]
    """Raw JSON Schema object describing the tool's arguments."""


# ---------------------------------------------------------------------------
# Normalised LLM response
# ---------------------------------------------------------------------------


class LLMResponse(BaseModel):
    """Provider-agnostic wrapper around an LLM completion response."""

    model_config = ConfigDict(frozen=True)

    message: AIMessage
    """The assistant turn, typed as the SDK's own AIMessage."""

    model: str
    """Exact model identifier that produced the response."""

    input_tokens: int
    output_tokens: int

    stop_reason: str
    """Normalised stop reason: ``end_turn``, ``tool_use``, or ``max_tokens``."""


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):
    """Interface every LLM provider must satisfy.

    The agent loop is typed against this Protocol — it never touches
    OllamaProvider directly.
    """

    async def complete(
        self,
        history: MessageHistory,
        tools: list[ToolSchema] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse: ...


# ---------------------------------------------------------------------------
# Finish-reason normalisation (OpenAI/Ollama → SDK canonical names)
# ---------------------------------------------------------------------------

_FINISH_REASON_MAP: dict[str, str] = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "length": "max_tokens",
}


# ---------------------------------------------------------------------------
# RetryConfig + CircuitBreaker + RetryableLLMProvider
# ---------------------------------------------------------------------------


class RetryConfig(BaseModel):
    """Configuration for retry behaviour and the circuit breaker.

    Attributes:
        max_retries: Maximum number of retry attempts on rate-limit errors.
        base_delay: Initial backoff delay in seconds (doubles each retry).
        max_delay: Upper cap on backoff delay in seconds.
        circuit_breaker_threshold: Consecutive failures before the circuit opens.
        circuit_breaker_timeout: Seconds to wait before attempting recovery.
    """

    model_config = ConfigDict(frozen=True)

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: float = 60.0


class _CBState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Three-state circuit breaker: CLOSED → OPEN → HALF_OPEN → CLOSED.

    Args:
        threshold: Consecutive failures before the circuit opens.
        timeout: Seconds in OPEN state before transitioning to HALF_OPEN.
    """

    def __init__(self, threshold: int = 5, timeout: float = 60.0) -> None:
        self._threshold = threshold
        self._timeout = timeout
        self._failures = 0
        self._state = _CBState.CLOSED
        self._opened_at: float | None = None

    def is_open(self) -> bool:
        """Return True when calls should be rejected (circuit is OPEN)."""
        if self._state == _CBState.CLOSED:
            return False
        if self._state == _CBState.OPEN:
            if time.monotonic() - (self._opened_at or 0.0) >= self._timeout:
                self._state = _CBState.HALF_OPEN
                return False
            return True
        # HALF_OPEN: allow one probe call through
        return False

    def record_success(self) -> None:
        """Reset failure count and close the circuit."""
        self._failures = 0
        self._state = _CBState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        """Increment failure count; open the circuit if threshold is reached."""
        self._failures += 1
        if self._state == _CBState.HALF_OPEN:
            # Failed during recovery probe → back to OPEN
            self._state = _CBState.OPEN
            self._opened_at = time.monotonic()
        elif self._failures >= self._threshold:
            self._state = _CBState.OPEN
            self._opened_at = time.monotonic()


class _BoundProvider:
    """Thin adapter so RetryableLLMProvider can wrap a bound method."""

    __slots__ = ("_fn",)

    def __init__(self, fn: Any) -> None:
        self._fn = fn

    async def complete(
        self,
        history: MessageHistory,
        tools: list[ToolSchema] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        return await self._fn(history, tools, max_tokens)


class RetryableLLMProvider:
    """Wraps any LLMProvider with exponential backoff and a circuit breaker.

    Args:
        provider: Any object satisfying the LLMProvider protocol.
        config: RetryConfig controlling delays and circuit-breaker thresholds.

    Example::

        llm = RetryableLLMProvider(
            provider=OllamaProvider(),
            config=RetryConfig(max_retries=5, base_delay=0.5),
        )
    """

    def __init__(
        self,
        provider: LLMProvider,
        config: RetryConfig | None = None,
    ) -> None:
        self._provider = provider
        self._config = config or RetryConfig()
        self._circuit = CircuitBreaker(
            threshold=self._config.circuit_breaker_threshold,
            timeout=self._config.circuit_breaker_timeout,
        )

    async def complete(
        self,
        history: MessageHistory,
        tools: list[ToolSchema] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Call the wrapped provider with retry and circuit-breaker logic."""
        if self._circuit.is_open():
            raise LLMProviderError(
                "Circuit breaker OPEN — too many consecutive failures. "
                f"Retry after {self._config.circuit_breaker_timeout}s."
            )

        last_exc: Exception | None = None

        for attempt in range(self._config.max_retries + 1):
            try:
                result = await self._provider.complete(history, tools, max_tokens)
                self._circuit.record_success()
                return result
            except LLMAuthError:
                # Auth errors are never retried and don't count against the circuit.
                raise
            except LLMRateLimitError as exc:
                last_exc = exc
                if attempt < self._config.max_retries:
                    delay = min(
                        self._config.base_delay * (2 ** attempt),
                        self._config.max_delay,
                    )
                    jitter = random.uniform(0, 0.1 * delay)
                    await asyncio.sleep(delay + jitter)

        self._circuit.record_failure()
        raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Ollama provider
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# XML text-mode tool-call parser (LLaMA chat-template fallback)
# ---------------------------------------------------------------------------

_XML_TOOL_RE = re.compile(r"<function/(\w+)")
# Matches the closing body format: <function/name>JSON_BODY</function>
_XML_TOOL_BODY_RE = re.compile(r"<function/(\w+)>(.*?)</function>", re.DOTALL)


def _parse_xml_tool_calls(content: str) -> list[ToolCall]:
    """Parse LLaMA-style XML tool calls from plain-text model content.

    Handles two formats some LLaMA-family models emit when they fall back to
    their internal chat-template format:
      Format A (inline JSON): <function/tool_name{"arg": "val"}></function>
      Format B (body JSON):   <function/tool_name>{"arg": "val"}</function>

    Returns an empty list when no valid tool calls are found.
    """
    decoder = json.JSONDecoder()
    tool_calls: list[ToolCall] = []
    seen_positions: set[int] = set()

    # ── Format B: <function/name>JSON</function> ──────────────────────────
    for match in _XML_TOOL_BODY_RE.finditer(content):
        name = match.group(1)
        body = match.group(2).strip()
        try:
            arguments, _ = decoder.raw_decode(body)
        except json.JSONDecodeError:
            continue
        if not isinstance(arguments, dict):
            continue
        tool_calls.append(ToolCall(
            id=f"xml_{uuid.uuid4().hex[:8]}",
            name=name,
            arguments=arguments,
        ))
        seen_positions.add(match.start())

    # ── Format A: <function/name{...}></function> ─────────────────────────
    for match in _XML_TOOL_RE.finditer(content):
        if match.start() in seen_positions:
            continue  # already handled by Format B
        name = match.group(1)
        json_start = match.end()
        if json_start >= len(content) or content[json_start] != "{":
            continue
        try:
            arguments, _ = decoder.raw_decode(content, json_start)
        except json.JSONDecodeError:
            continue
        if not isinstance(arguments, dict):
            continue
        tool_calls.append(ToolCall(
            id=f"xml_{uuid.uuid4().hex[:8]}",
            name=name,
            arguments=arguments,
        ))

    return tool_calls


# ---------------------------------------------------------------------------
# Text-mode tool injection helpers (fallback for models without native tools)
# ---------------------------------------------------------------------------

def _build_tool_injection_prompt(tools: list[ToolSchema]) -> str:
    """Build a system prompt block describing tools for text-mode tool calling.

    Used when the model does not support the OpenAI tool schema.  The model is
    instructed to emit ``TOOL_CALL: <JSON>`` lines instead of structured calls.
    """
    lines = [
        "You have access to the following tools. To call a tool, output EXACTLY one line:",
        "TOOL_CALL: {\"name\": \"<tool_name>\", \"arguments\": {<args_as_json>}}",
        "Output only the TOOL_CALL line — no other text on that line. "
        "Wait for the tool result before continuing.",
        "",
        "Available tools:",
    ]
    for t in tools:
        props = t.parameters.get("properties", {})
        arg_list = ", ".join(
            f"{k}: {v.get('type', 'any')}" for k, v in props.items()
        )
        lines.append(f"  - {t.name}({arg_list}): {t.description}")
    return "\n".join(lines)


_TEXT_TOOL_CALL_RE = re.compile(r"TOOL_CALL:\s*(\{)", re.IGNORECASE)


def _parse_text_tool_calls(content: str) -> list[ToolCall]:
    """Extract ``TOOL_CALL: <JSON>`` lines from plain model text.

    Uses JSONDecoder.raw_decode so nested objects are handled correctly.
    Returns an empty list when no valid tool calls are found.
    """
    decoder = json.JSONDecoder()
    tool_calls: list[ToolCall] = []
    for match in _TEXT_TOOL_CALL_RE.finditer(content):
        # raw_decode from the opening brace position
        json_start = match.start(1)
        try:
            obj, _ = decoder.raw_decode(content, json_start)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        name = obj.get("name")
        arguments = obj.get("arguments", {})
        if not name or not isinstance(arguments, dict):
            continue
        tool_calls.append(ToolCall(
            id=f"txt_{uuid.uuid4().hex[:8]}",
            name=name,
            arguments=arguments,
        ))
    return tool_calls


def _strip_tool_call_lines(content: str) -> str:
    """Remove ``TOOL_CALL: <JSON>`` spans from *content* using raw_decode.

    Strips everything from ``TOOL_CALL:`` to the end of the JSON object so
    the remaining text is clean prose without partial JSON fragments.
    """
    decoder = json.JSONDecoder()
    result = content
    # Iterate in reverse so span indices stay valid after each removal.
    spans: list[tuple[int, int]] = []
    for match in _TEXT_TOOL_CALL_RE.finditer(content):
        json_start = match.start(1)
        try:
            _, end_offset = decoder.raw_decode(content, json_start)
            spans.append((match.start(), end_offset))
        except json.JSONDecodeError:
            spans.append((match.start(), match.end()))

    for start, end in reversed(spans):
        # Also strip a trailing newline if present.
        tail = end if end >= len(result) or result[end] != "\n" else end + 1
        result = result[:start] + result[tail:]
    return result


class OllamaProvider:
    """LLM provider backed by a local Ollama server.

    Uses Ollama's OpenAI-compatible endpoint — no API key required.
    Ollama must be running (``ollama serve``) before calling :meth:`complete`.

    Args:
        model: Ollama model identifier. Defaults to ``llama3:8b``.
            Any model returned by ``ollama list`` can be used.
        base_url: Ollama server root URL. Defaults to the ``OLLAMA_HOST``
            environment variable, falling back to ``http://localhost:11434``.
        retry_config: Optional retry/circuit-breaker configuration.

    Example::

        llm = OllamaProvider()  # llama3:8b @ localhost:11434
        response = await llm.complete(history, max_tokens=512)

        # Use a different local model
        llm = OllamaProvider(model="deepseek-coder:6.7b")
    """

    def __init__(
        self,
        model: str = "llama3:8b",
        base_url: str | None = None,
        retry_config: RetryConfig | None = None,
    ) -> None:
        import httpx

        self._model = model
        resolved_url = (
            base_url
            or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        ).rstrip("/")
        self._base_url = resolved_url
        self._client = httpx.AsyncClient(base_url=resolved_url, timeout=120.0)
        self._retry_wrapper: RetryableLLMProvider | None = (
            RetryableLLMProvider(_BoundProvider(self._complete_once), retry_config)
            if retry_config else None
        )

    async def complete(
        self,
        history: MessageHistory,
        tools: list[ToolSchema] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Send *history* to Ollama, optionally via retry/circuit-breaker wrapper."""
        if self._retry_wrapper is not None:
            return await self._retry_wrapper.complete(history, tools, max_tokens)
        return await self._complete_once(history, tools, max_tokens)

    async def _complete_once(
        self,
        history: MessageHistory,
        tools: list[ToolSchema] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Single (non-retried) call to the Ollama /v1/chat/completions endpoint.

        If the model does not support native tool calling (Ollama returns 400),
        falls back to text-injection mode: tool schemas are described in a system
        prompt and the model is asked to emit ``TOOL_CALL: <JSON>`` lines.
        """
        import httpx

        payload: dict[str, Any] = {
            "model": self._model,
            # to_dict_list() already produces OpenAI-compatible dicts.
            "messages": history.to_dict_list(),
            "max_tokens": max_tokens,
            "stream": False,
        }

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        try:
            response = await self._client.post("/v1/chat/completions", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise LLMAuthError(str(exc)) from exc
            # ── Tool-call 400 fallback ────────────────────────────────────
            # Models like llama3:8b do not support the OpenAI tool schema over
            # Ollama's /v1 endpoint and return 400.  Retry without the tools
            # field and instead inject a text description so the model can still
            # call tools using a simple JSON line format.
            if exc.response.status_code == 400 and tools:
                return await self._complete_text_tool_mode(history, tools, max_tokens)
            raise LLMProviderError(str(exc)) from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(
                f"Cannot connect to Ollama at {self._base_url}. "
                "Make sure it is running: ollama serve"
            ) from exc

        return self._parse_response(response.json())

    async def _complete_text_tool_mode(
        self,
        history: MessageHistory,
        tools: list[ToolSchema],
        max_tokens: int,
    ) -> LLMResponse:
        """Fallback for models that reject native tool schemas.

        Describes tools in the system prompt and parses ``TOOL_CALL: <JSON>``
        lines from the plain-text response.  Tool-result messages (role=tool)
        are converted to plain user messages so the model can read them.
        """
        import httpx

        tool_block = _build_tool_injection_prompt(tools)

        # Convert the history to OpenAI-compatible dicts, then:
        #   1. Merge tool description block into the system message.
        #   2. Replace role="tool" messages with role="user" messages so
        #      models that don't understand the tool role can still read results.
        original_msgs = history.to_dict_list()
        messages: list[dict[str, Any]] = []
        for msg in original_msgs:
            if msg["role"] == "system":
                # Only inject the block into the first system message.
                if not any(m["role"] == "system" for m in messages):
                    messages.append({"role": "system", "content": tool_block + "\n\n" + msg["content"]})
                else:
                    messages.append(msg)
            elif msg["role"] == "tool":
                # Convert tool result to a human-readable user message.
                messages.append({
                    "role": "user",
                    "content": f"[Tool result]: {msg['content']}\nNow answer the user's question using this result.",
                })
            else:
                messages.append(msg)

        # If there was no system message, prepend the tool block.
        if not any(m["role"] == "system" for m in messages):
            messages.insert(0, {"role": "system", "content": tool_block})

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": False,
        }

        try:
            response = await self._client.post("/v1/chat/completions", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise LLMAuthError(str(exc)) from exc
            raise LLMProviderError(str(exc)) from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(
                f"Cannot connect to Ollama at {self._base_url}. "
                "Make sure it is running: ollama serve"
            ) from exc

        result = self._parse_response(response.json())

        # Parse TOOL_CALL lines from plain text if no structured calls came back.
        if not result.message.tool_calls and result.message.content:
            text_calls = _parse_text_tool_calls(result.message.content)
            if text_calls:
                # Strip TOOL_CALL lines — find each call's span and remove it.
                clean_content = _strip_tool_call_lines(result.message.content).strip()
                return LLMResponse(
                    message=AIMessage(content=clean_content, tool_calls=text_calls),
                    model=result.model,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    stop_reason="tool_use",
                )
        return result

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        """Convert a raw /v1/chat/completions response dict to LLMResponse."""
        choice = data["choices"][0]
        raw_msg: dict[str, Any] = choice["message"]
        finish_reason: str = choice.get("finish_reason") or "stop"
        content: str = raw_msg.get("content") or ""

        # Parse tool calls from the response into SDK-native ToolCall objects.
        parsed_tool_calls: list[ToolCall] = []
        for tc in raw_msg.get("tool_calls") or []:
            fn = tc["function"]
            try:
                arguments: dict[str, Any] = json.loads(fn.get("arguments") or "{}") or {}
            except (json.JSONDecodeError, TypeError):
                arguments = {"_raw": fn.get("arguments")}
            parsed_tool_calls.append(
                ToolCall(
                    id=tc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    name=fn["name"],
                    arguments=arguments,
                )
            )

        # ── XML text-mode tool-call fallback ──────────────────────────────
        # Some LLaMA variants fall back to their internal chat-template format
        # and emit tool calls as plain text. Convert them to ToolCall objects.
        if not parsed_tool_calls and "<function/" in content:
            parsed_tool_calls = _parse_xml_tool_calls(content)
            if parsed_tool_calls:
                finish_reason = "tool_calls"
                content = ""  # strip raw XML from the visible thought

        ai_message = AIMessage(
            content=content,
            tool_calls=parsed_tool_calls,
        )

        usage: dict[str, Any] = data.get("usage") or {}
        return LLMResponse(
            message=ai_message,
            model=data.get("model") or self._model,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            stop_reason=_FINISH_REASON_MAP.get(finish_reason, finish_reason),
        )


# ---------------------------------------------------------------------------
# Anthropic provider — stub
# ---------------------------------------------------------------------------


class AnthropicProvider:
    """Stub provider for Anthropic.

    Swap the ``complete`` body for the real implementation when moving to
    Anthropic in production — everything that imports ``AnthropicProvider``
    already type-checks correctly against ``LLMProvider``.
    """

    async def complete(
        self,
        history: MessageHistory,
        tools: list[ToolSchema] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        raise NotImplementedError("Switch to Anthropic in production")
