# Observability

agentsdk has built-in OpenTelemetry tracing via `TracedAgent`. Every LLM call and tool execution is wrapped in a span.

## Setup

```bash
pip install agentsdk[otel]
```

```python
import asyncio, os
from dotenv import load_dotenv
from agentsdk import AgentConfig, GroqProvider, DEFAULT_TOOLS
from agentsdk.observability import SDKTracer, TracedLLMProvider, TracedAgent, print_trace

load_dotenv()

tracer = SDKTracer(service_name="my-app")

llm = TracedLLMProvider(
    provider=GroqProvider(api_key=os.environ["GROQ_API_KEY"]),
    tracer=tracer,
)

agent = TracedAgent(
    config=AgentConfig(name="MyAgent", system_prompt="Use tools when needed."),
    llm=llm,
    registry=DEFAULT_TOOLS,
    tracer=tracer,
)

async def main():
    result, ctx = await agent.run("Get the current datetime and compute 12 * 12.")
    print(result.output)
    print_trace(ctx)

asyncio.run(main())
```

## print_trace() output

```
╔══════════════════════════════════════════════════════╗
║  Trace: MyAgent  [session: None]                     ║
║  Trace ID : a3f2b1c4d5e6f7a8b9c0d1e2f3a4b5c6       ║
║  Duration : 1842 ms                                  ║
║  LLM calls: 2  │  Tool calls: 2                      ║
║  Tokens   : 312 in  │  87 out                        ║
╚══════════════════════════════════════════════════════╝
```

## TraceContext fields

`agent.run()` returns `(AgentResult, TraceContext)` when using `TracedAgent`.

| Field | Description |
|---|---|
| `trace_id` | 32-char hex unique ID for this run |
| `agent_name` | Name from AgentConfig |
| `session_id` | Session ID passed to `run()` |
| `spans` | List of span names recorded |
| `started_at` | UTC datetime when `run()` was called |
| `finished_at` | UTC datetime when `run()` returned |
| `total_llm_calls` | Number of LLM completions |
| `total_tool_calls` | Number of tool dispatches |
| `total_input_tokens` | Cumulative prompt tokens |
| `total_output_tokens` | Cumulative completion tokens |

## Export to a collector

Pass `export_to_console=True` to print raw OTel spans to stdout, or wire in your own exporter:

```python
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

tracer = SDKTracer(service_name="my-app")
tracer.get_tracer()  # raw OTel tracer for custom span processors
```
