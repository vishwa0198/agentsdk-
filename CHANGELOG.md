# Changelog

## [0.2.0] — 2026-05-20

### Added
- `github_get_repo` — fetch repo metadata (stars, forks, issues)
- `github_list_issues` — list open/closed issues
- `github_create_issue` — create issues via API
- `github_get_file` — read file contents from any repo
- `scrape_webpage` — CSS-selector-based text extraction
- `extract_links` — extract and resolve all hyperlinks
- `sql_query` — run SELECT/INSERT/UPDATE against SQLite or PostgreSQL
- `sql_schema` — inspect table structure of any database

## [0.1.2] — 2026-05-20

### Added
- Docker sandbox for `run_python` — no network, read-only filesystem, 128 MB memory cap
- `RetryableLLMProvider` — exponential backoff with jitter on rate-limit errors
- `CircuitBreaker` — auto-opens after 5 consecutive failures, recovers after 60 s
- `RetryConfig` — configurable retry and circuit-breaker settings
- Integration test suite — 8 tests hitting real Groq API

### Changed
- `run_python` now requires Docker by default. Set `AGENTSDK_UNSAFE_PYTHON=1` to use the old subprocess method

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
