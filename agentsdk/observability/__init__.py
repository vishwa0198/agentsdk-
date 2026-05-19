"""agentsdk/observability — OpenTelemetry Tracing Layer.

Public surface:

    AgentSpan           — span attribute name constants
    SDKTracer           — thin OTel TracerProvider wrapper
    TraceContext        — run-scoped aggregated trace state (dataclass)
    TracedLLMProvider   — LLMProvider decorator that adds a ``llm.complete`` span
    TracedAgent         — Agent subclass with per-step and per-tool spans
    print_trace         — human-readable TraceContext console printer
"""

from agentsdk.observability.tracer import (
    AgentSpan,
    SDKTracer,
    TraceContext,
    TracedLLMProvider,
)
from agentsdk.observability.middleware import TracedAgent, print_trace

__all__ = [
    "AgentSpan",
    "SDKTracer",
    "TraceContext",
    "TracedAgent",
    "TracedLLMProvider",
    "print_trace",
]
