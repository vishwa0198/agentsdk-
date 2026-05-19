# Changelog

## [0.1.0] — 2026-05-19

### Added
- Core ReAct agent loop (`Agent`, `AgentConfig`, `AgentResult`)
- Typed message model (`MessageHistory`, `HumanMessage`, `AIMessage`, `SystemMessage`, `ToolResultMessage`)
- LLM provider abstraction with Groq backend (`GroqProvider`)
- Tool system — `@tool` decorator, `ToolRegistry`, schema auto-generation from type hints
- Built-in tools — `run_python`, `http_request`, `read_file`, `write_file`, `get_datetime`
- Multi-agent DAG pipeline (`AgentGraph`, `GraphRunner`)
- Async message bus with request/reply (`MessageBus`, `BusAwareAgent`, `BusRunner`)
- Persistent sessions with checkpointing and fork/resume (`FileCheckpointStore`, `SessionManager`)
- OpenTelemetry tracing (`TracedAgent`, `TracedLLMProvider`, `SDKTracer`)
- CLI — `scaffold-agent new`, `run`, `trace`, `list-sessions`
