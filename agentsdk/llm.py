"""agentsdk/llm.py

LLM provider abstraction — Groq backend with a swappable Protocol interface.

Import chain:
    agent loop → LLMProvider (Protocol)
                  └── GroqProvider (concrete)
                  └── AnthropicProvider (stub)

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
    GroqProvider or AnthropicProvider directly.
    """

    async def complete(
        self,
        history: MessageHistory,
        tools: list[ToolSchema] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse: ...


# ---------------------------------------------------------------------------
# Finish-reason normalisation (Groq/OpenAI → SDK canonical names)
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
            provider=GroqProvider(api_key="..."),
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
# Groq provider
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# XML text-mode tool-call parser
# ---------------------------------------------------------------------------

_XML_TOOL_RE = re.compile(r"<function/(\w+)")
# Matches the closing body format: <function/name>JSON_BODY</function>
_XML_TOOL_BODY_RE = re.compile(r"<function/(\w+)>(.*?)</function>", re.DOTALL)


def _parse_xml_tool_calls(content: str) -> list[ToolCall]:
    """Parse LLaMA-style XML tool calls from plain-text model content.

    Handles two formats emitted by Groq-hosted models:
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


class GroqProvider:
    """LLM provider backed by Groq's async Python SDK.

    Args:
        api_key: Groq API key. Defaults to the ``GROQ_API_KEY`` environment variable.
        model: Groq model identifier. Defaults to ``llama-3.3-70b-versatile``.
        fallback_models: Ordered list of model IDs to try when the primary hits a
            rate limit. Rotation is automatic and transparent to the caller.

    Example::

        import os
        llm = GroqProvider(api_key=os.environ["GROQ_API_KEY"])
        response = await llm.complete(history, max_tokens=512)
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "llama-3.3-70b-versatile",
        retry_config: RetryConfig | None = None,
        fallback_models: list[str] | None = None,
    ) -> None:
        try:
            import groq as _groq
            from groq import AsyncGroq
        except ImportError as exc:
            raise ImportError(
                "groq is not installed. Run: pip install groq"
            ) from exc

        self._model = model
        # All models in priority order: primary first, then fallbacks.
        self._model_chain: list[str] = [model] + (fallback_models or [])
        self._model_idx: int = 0  # index into _model_chain currently in use
        # Resolve the key once at construction time; fail fast if absent.
        resolved_key = api_key or os.environ.get("GROQ_API_KEY")
        self._client = AsyncGroq(api_key=resolved_key)
        # Keep a reference to the module so complete() can catch its errors.
        self._groq = _groq
        # Wrap with retry/circuit-breaker if a config was provided.
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
        """Send *history* to Groq, optionally via retry/circuit-breaker wrapper."""
        if self._retry_wrapper is not None:
            return await self._retry_wrapper.complete(history, tools, max_tokens)
        return await self._complete_once(history, tools, max_tokens)

    async def _complete_once(
        self,
        history: MessageHistory,
        tools: list[ToolSchema] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Single (non-retried) call to the Groq API."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            # to_dict_list() already produces OpenAI-compatible dicts, which
            # Groq accepts unchanged — zero transformation needed here.
            "messages": history.to_dict_list(),
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = [
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
            response = await self._client.chat.completions.create(**kwargs)
        except self._groq.RateLimitError as exc:
            # Auto-rotate to the next model in the fallback chain.
            if self._model_idx < len(self._model_chain) - 1:
                prev = self._model_chain[self._model_idx]
                self._model_idx += 1
                self._model = self._model_chain[self._model_idx]
                kwargs["model"] = self._model
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "Rate limit on %s — auto-switching to fallback model %s", prev, self._model
                )
                try:
                    response = await self._client.chat.completions.create(**kwargs)
                except self._groq.RateLimitError as exc2:
                    raise LLMRateLimitError(str(exc2)) from exc2
            else:
                raise LLMRateLimitError(str(exc)) from exc
        except self._groq.AuthenticationError as exc:
            raise LLMAuthError(str(exc)) from exc
        except self._groq.APIError as exc:
            raise LLMProviderError(str(exc)) from exc

        choice = response.choices[0]
        raw_msg = choice.message
        finish_reason: str = choice.finish_reason or "stop"
        content: str = raw_msg.content or ""

        # Parse tool calls from the response into SDK-native ToolCall objects.
        parsed_tool_calls: list[ToolCall] = []
        if raw_msg.tool_calls:
            for tc in raw_msg.tool_calls:
                try:
                    # arguments may be None or JSON null for zero-parameter tools.
                    arguments: dict[str, Any] = json.loads(tc.function.arguments or "{}") or {}
                except (json.JSONDecodeError, TypeError):
                    # Malformed JSON from the model — preserve raw string.
                    arguments = {"_raw": tc.function.arguments}
                parsed_tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=arguments,
                    )
                )

        # ── XML text-mode tool-call fallback ──────────────────────────────
        # Some Groq-hosted LLaMA variants fall back to their internal chat-
        # template format and emit tool calls as plain text:
        #   <function/tool_name{"arg": "val"}></function>
        # When no structured tool_calls were parsed but the content contains
        # this pattern, convert them to proper ToolCall objects so the agent
        # loop can dispatch them normally.
        if not parsed_tool_calls and "<function/" in content:
            parsed_tool_calls = _parse_xml_tool_calls(content)
            if parsed_tool_calls:
                finish_reason = "tool_calls"  # treat as tool_use
                content = ""  # strip raw XML from the visible thought

        ai_message = AIMessage(
            # content may be None when the model only emits tool calls.
            content=content,
            tool_calls=parsed_tool_calls,
        )

        usage = response.usage
        return LLMResponse(
            message=ai_message,
            model=response.model or self._model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
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
