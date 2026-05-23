# agentsdk

[![PyPI version](https://badge.fury.io/py/agentsdk-py.svg)](https://pypi.org/project/agentsdk-py/)
[![Python](https://img.shields.io/pypi/pyversions/agentsdk-py)](https://pypi.org/project/agentsdk-py/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-live-blue)](https://vishwa0198.github.io/agentsdk)

A lightweight Python SDK for building AI agents with tool use, multi-agent graphs, persistence, and tracing.

## Install

```bash
pip install agentsdk          # core
pip install agentsdk[otel]    # + OpenTelemetry tracing
pip install agentsdk[dev]     # + pytest / dotenv
```

## Quickstart

```python
import asyncio, os
from agentsdk import Agent, AgentConfig, GroqProvider

agent = Agent(
    config=AgentConfig(
        name="MyAgent",
        system_prompt="You are a helpful assistant.",
    ),
    llm=GroqProvider(api_key=os.environ["GROQ_API_KEY"]),
)

async def main():
    result = await agent.run("What is the capital of France?")
    print(result.output)

asyncio.run(main())
```

## Tools

```python
from agentsdk import tool, ToolRegistry, Agent, AgentConfig, GroqProvider

@tool
async def add(a: int, b: int) -> str:
    """Add two integers."""
    return str(a + b)

registry = ToolRegistry()
registry.register(add)

agent = Agent(config=AgentConfig(name="Calc", system_prompt="Use tools."),
              llm=GroqProvider(...), registry=registry)
```

## Multi-agent Graph

```python
from agentsdk import AgentNode, Edge, AgentGraph, GraphRunner

graph = AgentGraph()
graph.add_node(AgentNode("researcher", researcher_agent))
graph.add_node(AgentNode("writer", writer_agent))
graph.add_edge(Edge("researcher", "writer", data_map={"output": "input"}))
graph.set_entry("researcher"); graph.set_exit("writer")
result = await GraphRunner(graph).run({"input": "Explain black holes"})
```

## Persistence

```python
from agentsdk import FileCheckpointStore, SessionManager, Agent

store = FileCheckpointStore(base_dir=".agentsdk/checkpoints")
session_mgr = SessionManager(store=store, agent_name="MyAgent")
agent = Agent(config=..., llm=..., session_manager=session_mgr)

# History is saved and reloaded automatically across runs:
await agent.run("My favourite language is Python.", session_id="user-001")
await agent.run("What language did I mention?",     session_id="user-001")

# Fork a session to branch an agent run:
forked = await session_mgr.fork("user-001", "user-001-branch")
```

## Tracing (requires `agentsdk[otel]`)

```python
from agentsdk.observability import SDKTracer, TracedLLMProvider, TracedAgent, print_trace

tracer     = SDKTracer(service_name="myapp")
traced_llm = TracedLLMProvider(provider=GroqProvider(...), tracer=tracer)
agent      = TracedAgent(config=..., llm=traced_llm, tracer=tracer)

result, ctx = await agent.run("Summarise the last quarter earnings.")
print_trace(ctx)
# ╔══ Trace: MyAgent ══════════════════════
# ║  Session     : (none)
# ║  Trace ID    : 6744d6eca33853c5bba0...
# ║  Duration    : 3680ms
# ║  LLM calls   : 2
# ║  Tool calls  : 1
# ║  Tokens      : 1292 in / 36 out
# ╚═════════════════════════════════════════
```

## CLI

```bash
# Scaffold a new agent project
scaffold-agent new myproject

# Interactive REPL against any agent file
scaffold-agent run myproject/agents/main.py

# Inspect a saved checkpoint
scaffold-agent trace .agentsdk/checkpoints/MyAgent/user-001.json

# List all sessions for an agent
scaffold-agent list-sessions MyAgent
```

## Web UI

A full-featured chat interface ships alongside the SDK — agents, memory, MCP
tool servers, multi-agent pipelines, schedules, and live monitoring in one UI.

```bash
cd webui
cp .env.example .env          # fill in GROQ_API_KEY and SECRET_KEY
docker compose up --build     # backend :8000, frontend :3000
```

**Features:**

| | |
|---|---|
| 💬 Chat | Streaming WebSocket chat with any configured agent |
| 🧠 Memory | Visualise RAG memory, semantic search, drag-and-drop file ingest |
| 🔌 MCP | Connect any MCP server (Filesystem, Postgres, custom SSE/stdio) |
| 🔗 Pipeline | Visual node-editor for multi-agent pipelines with auto-wire |
| ⏱ Schedule | Cron/interval schedules with webhook triggers and run history |
| 📊 Monitor | Live run metrics, token usage, latency charts |

For local development without Docker:

```bash
# Backend
cd webui/backend && pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd webui/frontend && npm install && npm run dev
```

## Contributing

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for setup instructions and
contribution guidelines.

## License

MIT
