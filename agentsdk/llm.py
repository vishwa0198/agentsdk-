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

import json
import os
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
# Groq provider
# ---------------------------------------------------------------------------


class GroqProvider:
    """LLM provider backed by Groq's async Python SDK.

    Args:
        api_key: Groq API key. Defaults to the ``GROQ_API_KEY`` environment variable.
        model: Groq model identifier. Defaults to ``llama-3.3-70b-versatile``.

    Example::

        import os
        llm = GroqProvider(api_key=os.environ["GROQ_API_KEY"])
        response = await llm.complete(history, max_tokens=512)
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "llama-3.3-70b-versatile",
    ) -> None:
        try:
            import groq as _groq
            from groq import AsyncGroq
        except ImportError as exc:
            raise ImportError(
                "groq is not installed. Run: pip install groq"
            ) from exc

        self._model = model
        # Resolve the key once at construction time; fail fast if absent.
        resolved_key = api_key or os.environ.get("GROQ_API_KEY")
        self._client = AsyncGroq(api_key=resolved_key)
        # Keep a reference to the module so complete() can catch its errors.
        self._groq = _groq

    async def complete(
        self,
        history: MessageHistory,
        tools: list[ToolSchema] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Send *history* to Groq and return a normalised :class:`LLMResponse`."""
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
            raise LLMRateLimitError(str(exc)) from exc
        except self._groq.AuthenticationError as exc:
            raise LLMAuthError(str(exc)) from exc
        except self._groq.APIError as exc:
            raise LLMProviderError(str(exc)) from exc

        choice = response.choices[0]
        raw_msg = choice.message
        finish_reason: str = choice.finish_reason or "stop"

        # Parse tool calls from the response into SDK-native ToolCall objects.
        parsed_tool_calls: list[ToolCall] = []
        if raw_msg.tool_calls:
            for tc in raw_msg.tool_calls:
                try:
                    # arguments may be None for zero-parameter tools; fall back to {}
                    arguments: dict[str, Any] = json.loads(tc.function.arguments or "{}")
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

        ai_message = AIMessage(
            # content may be None when the model only emits tool calls.
            content=raw_msg.content or "",
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
