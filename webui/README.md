# agentsdk Web UI

A full-stack chat interface for agentsdk agents — FastAPI backend with WebSocket streaming, React frontend, and Docker Compose deployment.

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + uvicorn, WebSocket streaming |
| Agent | agentsdk (GroqProvider, RAGMemory, FileCheckpointStore) |
| Frontend | React 18 + Vite, react-markdown, react-syntax-highlighter |
| Serving | nginx (prod) / Vite dev server (local) |
| Deployment | Docker Compose |

## Run with Docker Compose

```bash
cd webui

# Copy the env template and add your key
cp .env.example .env
# Edit .env → set GROQ_API_KEY=gsk_...

docker-compose up --build
```

Then open:
- **Chat UI**: http://localhost:3000
- **API docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/health

> **run_python sandboxing**: The compose file mounts `/var/run/docker.sock` so
> the backend can launch isolated Docker containers for code execution. If Docker
> is not available, add `AGENTSDK_UNSAFE_PYTHON=1` to the backend environment in
> `docker-compose.yml` to use a local subprocess fallback.

## Run locally (no Docker)

### Backend

```bash
cd webui/backend
pip install -r requirements.txt
# Ensure GROQ_API_KEY is set in ../../.env or the environment
AGENTSDK_UNSAFE_PYTHON=1 uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd webui/frontend
npm install
npm run dev        # starts on http://localhost:3000
```

The Vite dev server proxies `/chat`, `/sessions`, `/health`, and `/ws/*` to
`localhost:8000` automatically — no CORS issues.

## API reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/chat` | Synchronous chat — full result |
| `WS` | `/ws/{session_id}` | Streaming chat — real-time events |
| `GET` | `/sessions/{agent_name}` | List persisted sessions |
| `DELETE` | `/sessions/{session_id}` | Delete session + vector data |
| `GET` | `/health` | Liveness probe |

### WebSocket event stream

```
client → server:  {"message": "...", "agent_name": "WebAgent"}

server → client (one or more):
  {"type": "step",        "data": {"iteration": 1, "thought": "..."}}
  {"type": "tool_call",   "data": {"name": "run_python", "arguments": {...}}}
  {"type": "tool_result", "data": {"name": "run_python", "result": "...", "is_error": false}}
  {"type": "final",       "data": {"output": "...", "steps": 3, "tokens": {"input": 842, "output": 231}}}
  {"type": "error",       "data": {"message": "..."}}
```

## Project structure

```
webui/
├── backend/
│   ├── main.py            FastAPI app — REST + WebSocket endpoints
│   ├── agent_manager.py   Manages Agent instances per session
│   ├── models.py          Pydantic request/response models
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.jsx              Root shell — layout, state, WebSocket handler
│   │   ├── index.css            Dark-theme design system
│   │   ├── main.jsx             React entry point
│   │   └── components/
│   │       ├── ChatWindow.jsx   Message list + textarea input
│   │       ├── MessageBubble.jsx Markdown bubbles with syntax highlighting
│   │       ├── ToolCallTrace.jsx Expandable tool-call cards
│   │       ├── SessionSidebar.jsx Session list + new/delete
│   │       └── TokenCounter.jsx  Live input/output token display
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── nginx.conf         Production nginx config (proxies /ws/ + REST)
│   └── Dockerfile         Multi-stage: node build → nginx serve
├── docker-compose.yml
├── .env.example
└── README.md
```
