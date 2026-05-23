"""agentsdk/observability/tracer.py

AgentSpan constants, SDKTracer, TraceContext, TracedLLMProvider.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.trace import Tracer

from agentsdk.llm import LLMProvider, LLMResponse, ToolSchema
from agentsdk.messages import MessageHistory


# ---------------------------------------------------------------------------
# AgentSpan — span attribute name constants
# ---------------------------------------------------------------------------


class AgentSpan:
    """Class-level string constants for OTel span attribute names.

    Use these instead of bare strings to keep attribute names consistent
    across the entire codebase.
    """

    # Agent
    AGENT_NAME = "agent.name"
    AGENT_SESSION = "agent.session_id"
    AGENT_ITERATION = "agent.iteration"
    AGENT_STOPPED_BY = "agent.stopped_by"

    # LLM
    LLM_MODEL = "llm.model"
    LLM_INPUT_TOKENS = "llm.input_tokens"
    LLM_OUTPUT_TOKENS = "llm.output_tokens"
    LLM_STOP_REASON = "llm.stop_reason"

    # Tool
    TOOL_NAME = "tool.name"
    TOOL_SUCCESS = "tool.success"
    TOOL_ERROR = "tool.error"


# ---------------------------------------------------------------------------
# SDKTracer — thin OTel wrapper
# ---------------------------------------------------------------------------


class SDKTracer:
    """Thin wrapper around an OpenTelemetry TracerProvider.

    Parameters
    ----------
    service_name:
        Appears as ``service.name`` in every span.
    export_to_console:
        When True, attach a ``ConsoleSpanExporter`` (synchronous) so raw
        OTel span JSON is printed to stdout — useful during development.
    """

    def __init__(
        self,
        service_name: str = "agentsdk",
        export_to_console: bool = False,
    ) -> None:
        resource = Resource.create({"service.name": service_name})
        self._provider = TracerProvider(resource=resource)

        if export_to_console:
            self._provider.add_span_processor(
                SimpleSpanProcessor(ConsoleSpanExporter())
            )

        # Obtain tracer directly from the provider (no global mutation).
        self._tracer: Tracer = self._provider.get_tracer(service_name)

    def span(self, name: str):
        """Return an OTel span context manager via ``start_as_current_span``."""
        return self._tracer.start_as_current_span(name)

    def get_tracer(self) -> Tracer:
        """Return the raw OTel Tracer for advanced use."""
        return self._tracer


# ---------------------------------------------------------------------------
# TraceContext — run-scoped trace state
# ---------------------------------------------------------------------------


@dataclass
class TraceContext:
    """Aggregated trace state for one ``Agent.run()`` invocation.

    Built by ``TracedAgent`` and returned alongside the normal
    ``AgentResult``.
    """

    trace_id: str
    """32-char hex string of the OTel trace ID, or empty string if unavailable."""

    agent_name: str
    session_id: str | None

    spans: list[str]
    """Ordered list of span names opened during this run."""

    started_at: datetime
    finished_at: datetime | None = None

    total_llm_calls: int = 0
    total_tool_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


# ---------------------------------------------------------------------------
# TracedLLMProvider — wraps any LLMProvider with an OTel span
# ---------------------------------------------------------------------------


class TracedLLMProvider:
    """Decorates any ``LLMProvider`` with a ``llm.complete`` OTel span.

    The wrapped provider's response is returned unchanged; this class only
    adds observability.

    Usage
    -----
    ::

        tracer = SDKTracer()
        traced_llm = TracedLLMProvider(provider=groq_provider, tracer=tracer)
        agent = TracedAgent(config=cfg, llm=traced_llm, tracer=tracer)
    """

    def __init__(self, provider: LLMProvider, tracer: SDKTracer) -> None:
        self._provider = provider
        self._tracer = tracer

    async def complete(
        self,
        history: MessageHistory,
        tools: list[ToolSchema] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        from opentelemetry.trace import StatusCode

        with self._tracer.span("llm.complete") as span:
            try:
                response = await self._provider.complete(
                    history, tools=tools, max_tokens=max_tokens
                )
                span.set_attribute(AgentSpan.LLM_MODEL, response.model)
                span.set_attribute(AgentSpan.LLM_INPUT_TOKENS, response.input_tokens)
                span.set_attribute(AgentSpan.LLM_OUTPUT_TOKENS, response.output_tokens)
                span.set_attribute(AgentSpan.LLM_STOP_REASON, response.stop_reason)
                return response
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(StatusCode.ERROR)
                raise
