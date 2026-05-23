"""webui/backend/main.py — FastAPI application with REST + WebSocket endpoints."""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm

from agent_manager import AgentManager
from mcp_manager import MCPManager
from pipeline_manager import PipelineManager
from metrics_store import MetricsStore, build_record
from file_handler import build_file_context, extract_text
from scheduler import Scheduler, ScheduleConfig
from auth import create_access_token, decode_token, get_current_user, user_store
from agentsdk.memory.vector_store import VectorMemoryStore, _make_doc_id
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from models import (
    AddMCPServerRequest,
    ChatRequest,
    ChatResponse,
    CreateScheduleRequest,
    FileUploadResult,
    PipelineConfig,
    PipelineRunRequest,
    PipelineRunResult,
    RegisterRequest,
    ScheduleResponse,
    SessionInfo,
    StreamEvent,
    TokenResponse,
    UserInfo,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

manager = AgentManager()
mcp_manager = MCPManager()
pipeline_manager = PipelineManager()
metrics = MetricsStore()
scheduler = Scheduler(manager, metrics)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start scheduler tasks on startup; stop them on shutdown."""
    scheduler.start_all()
    yield
    scheduler.stop_all()


# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

# Allowed origins: comma-separated list via env var.
# Default to localhost:3000 for local dev; set explicitly in production.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",")]

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="agentsdk Web UI",
    description="Chat with agentsdk agents over REST and WebSocket.",
    version="0.1.2",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    """Liveness probe."""
    return {"status": "ok", "version": "0.2.0"}


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest) -> dict:
    try:
        user_store.add_user(body.username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "registered"}


@app.post("/auth/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    if not user_store.verify_login(form.username, form.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": form.username})
    return TokenResponse(access_token=token)


@app.get("/auth/me", response_model=UserInfo)
async def me(current_user: str = Depends(get_current_user)) -> UserInfo:
    user = user_store.get_user(current_user)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return UserInfo(username=user.username, created_at=user.created_at)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: str = Depends(get_current_user),
) -> ChatResponse:
    """Synchronous chat — run the full agent loop and return a complete result."""
    session_key = f"{current_user}__{request.session_id}"
    agent = manager.get_or_create(session_key, request.agent_name)
    result = await agent.run(request.message, session_id=session_key)
    return ChatResponse(
        session_id=request.session_id,
        output=result.output,
        steps=len(result.steps),
        input_tokens=result.total_input_tokens,
        output_tokens=result.total_output_tokens,
        stopped_by=result.stopped_by,
    )


@app.get("/sessions/{agent_name}", response_model=list[SessionInfo])
async def list_sessions(
    agent_name: str,
    current_user: str = Depends(get_current_user),
) -> list[SessionInfo]:
    """Return metadata for all persisted sessions of *agent_name* owned by this user."""
    all_sessions = await manager.list_sessions(agent_name)
    prefix = f"{current_user}__"
    user_sessions = [s for s in all_sessions if s.session_id.startswith(prefix)]
    # Strip the username prefix before returning to client
    for s in user_sessions:
        s.session_id = s.session_id[len(prefix):]
    return user_sessions


@app.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Delete a session's checkpoint and vector data."""
    session_key = f"{current_user}__{session_id}"
    await manager.delete_session(session_key)
    return {"deleted": session_id}


# ---------------------------------------------------------------------------
# Memory endpoints
# ---------------------------------------------------------------------------

def _memory_store(current_user: str, session_id: str) -> tuple[VectorMemoryStore, str]:
    """Return (store, session_key) for the given user + session."""
    chroma_name = f"{current_user}__{session_id}"
    session_key = f"{current_user}__{session_id}"
    return VectorMemoryStore(collection_name=chroma_name), session_key


@app.get("/memory/{session_id}/search")
async def search_memory(
    session_id: str,
    q: str,
    n: int = 5,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Semantic search over stored memories for a session."""
    store, session_key = _memory_store(current_user, session_id)
    results = await store.search(session_key, query=q, n_results=n)
    return {
        "query": q,
        "results": [
            {
                "role": msg.role.value,
                "content": msg.content,
                "preview": msg.content[:120] + "..." if len(msg.content) > 120 else msg.content,
                "created_at": msg.created_at.isoformat(),
            }
            for msg in results
        ],
    }


@app.get("/memory/{session_id}/stats")
async def get_memory_stats(
    session_id: str,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Return aggregate stats for a session's memory."""
    store, session_key = _memory_store(current_user, session_id)
    messages = await store.get_all(session_key)
    return {
        "session_id": session_id,
        "total_memories": len(messages),
        "oldest": min(m.created_at for m in messages).isoformat() if messages else None,
        "newest": max(m.created_at for m in messages).isoformat() if messages else None,
        "roles": {
            "system": sum(1 for m in messages if m.role.value == "system"),
            "human": sum(1 for m in messages if m.role.value == "human"),
            "ai": sum(1 for m in messages if m.role.value == "ai"),
            "tool_result": sum(1 for m in messages if m.role.value == "tool_result"),
        },
    }


@app.get("/memory/{session_id}")
async def get_memories(
    session_id: str,
    current_user: str = Depends(get_current_user),
) -> dict:
    """List all stored memories for a session in chronological order."""
    store, session_key = _memory_store(current_user, session_id)
    messages = await store.get_all(session_key)
    return {
        "session_id": session_id,
        "count": len(messages),
        "memories": [
            {
                "id": str(i),
                "role": msg.role.value,
                "content": msg.content,
                "created_at": msg.created_at.isoformat(),
                "preview": msg.content[:120] + "..." if len(msg.content) > 120 else msg.content,
            }
            for i, msg in enumerate(messages)
        ],
    }


@app.delete("/memory/{session_id}/{memory_id}")
async def delete_memory(
    session_id: str,
    memory_id: str,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Delete a single memory entry by its index id."""
    store, session_key = _memory_store(current_user, session_id)
    messages = await store.get_all(session_key)
    try:
        idx = int(memory_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="memory_id must be an integer") from exc
    if idx < 0 or idx >= len(messages):
        raise HTTPException(status_code=404, detail="Memory not found")
    doc_id = _make_doc_id(session_key, messages[idx])
    store._collection.delete(ids=[doc_id])
    return {"deleted": memory_id}


@app.delete("/memory/{session_id}")
async def clear_memory(
    session_id: str,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Delete all memories for a session."""
    store, session_key = _memory_store(current_user, session_id)
    await store.delete_session(session_key)
    return {"cleared": session_id}


@app.post("/memory/{session_id}/ingest", status_code=201)
async def ingest_file_to_memory(
    session_id: str,
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
) -> dict:
    """Ingest a file into a session's RAG memory.

    Extracts text from PDF/TXT/MD/code files and stores them as SystemMessage
    chunks in the session's vector store so the agent can semantically retrieve
    them during conversation.
    """
    from agentsdk.messages import SystemMessage  # local import avoids circular deps

    content = await file.read()
    info = extract_text(file.filename or "upload", content)
    text: str = info.get("text") or ""
    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail=f"Could not extract text from '{file.filename}'. Supported: txt, md, pdf, csv, py, js, json…",
        )

    store, session_key = _memory_store(current_user, session_id)

    # Chunk large texts so each ChromaDB document stays under the embedding limit.
    CHUNK = 1800
    chunks = [text[i : i + CHUNK] for i in range(0, len(text), CHUNK)]
    for idx, chunk in enumerate(chunks):
        header = f"[File: {info['filename']}"
        if len(chunks) > 1:
            header += f", part {idx + 1}/{len(chunks)}"
        header += "]\n\n"
        await store.add(session_key, SystemMessage(content=header + chunk))

    return {
        "filename": info["filename"],
        "type": info["type"],
        "chars": len(text),
        "chunks": len(chunks),
    }


# ---------------------------------------------------------------------------
# WebSocket streaming endpoint
# ---------------------------------------------------------------------------


@app.websocket("/ws/{session_id}")
async def websocket_chat(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(...),
) -> None:
    """Stream agent events in real-time over WebSocket.

    Auth: pass JWT as ?token=<jwt> query parameter.
    """
    username = decode_token(token)
    if not username:
        await websocket.close(code=1008)
        return

    session_key = f"{username}__{session_id}"

    await websocket.accept()

    try:
        payload = await websocket.receive_json()
        message: str = payload.get("message", "")
        agent_name: str = payload.get("agent_name", "WebAgent")
        system_prompt: str | None = payload.get("system_prompt") or None
        file_contexts: list[dict] = payload.get("files", [])  # [{file_id, filename, type, text, ...}]

        # Prepend uploaded file context blocks to the message
        if file_contexts:
            ctx_blocks = []
            for fc in file_contexts:
                block = build_file_context(fc)
                if block:
                    ctx_blocks.append(block)
            if ctx_blocks:
                message = "\n\n".join(ctx_blocks) + "\n\n" + message

        if not message.strip():
            await websocket.send_json(
                StreamEvent(type="error", data={"message": "Empty message."}).model_dump()
            )
            return

        agent = manager.get_or_create(session_key, agent_name, system_prompt=system_prompt)

        # Inject live MCP tools for this user before every run.
        mcp_tools = mcp_manager.get_tools(username)
        manager.sync_mcp_tools(session_key, mcp_tools)

        # Wire up the step callback to forward every event to the client.
        async def _emit(event_type: str, data: dict) -> None:
            await websocket.send_json(
                StreamEvent(type=event_type, data=data).model_dump()
            )

        agent._step_callback = _emit

        _started_at = time.monotonic()
        _started_wall = datetime.now(timezone.utc)
        _run_result = None
        _run_error: str | None = None

        try:
            _run_result = await agent.run(message, session_id=session_key)
        except Exception as exc:  # noqa: BLE001
            _run_error = str(exc)
            await websocket.send_json(
                StreamEvent(type="error", data={"message": str(exc)}).model_dump()
            )
        finally:
            agent._step_callback = None
            metrics.record(build_record(
                username=username,
                session_id=session_id,
                agent_name=agent_name,
                started_at=_started_at,
                started_wall=_started_wall,
                result=_run_result,
                error=_run_error,
            ))

    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        try:
            await websocket.send_json(
                StreamEvent(type="error", data={"message": str(exc)}).model_dump()
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# MCP server endpoints
# ---------------------------------------------------------------------------

@app.get("/mcp/servers")
async def list_mcp_servers(
    current_user: str = Depends(get_current_user),
) -> list[dict]:
    """List all configured MCP servers for the current user."""
    return mcp_manager.list_servers(current_user)


@app.post("/mcp/servers", status_code=201)
async def add_mcp_server(
    body: AddMCPServerRequest,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Register a new MCP server config (does not connect yet)."""
    server_id = await mcp_manager.add_server(current_user, body.model_dump())
    return {"id": server_id, "name": body.name}


@app.delete("/mcp/servers/{server_id}")
async def remove_mcp_server(
    server_id: str,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Disconnect (if connected) and remove the MCP server config."""
    try:
        await mcp_manager.remove_server(current_user, server_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"removed": server_id}


@app.post("/mcp/servers/{server_id}/connect")
async def connect_mcp_server(
    server_id: str,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Connect to an MCP server and return its available tools."""
    try:
        tools = await mcp_manager.connect(current_user, server_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"MCP connect failed: {exc}") from exc
    return {"connected": True, "tools": tools}


@app.post("/mcp/servers/{server_id}/disconnect")
async def disconnect_mcp_server(
    server_id: str,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Disconnect from an MCP server."""
    try:
        await mcp_manager.disconnect(current_user, server_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"disconnected": True}


# ---------------------------------------------------------------------------
# Pipeline endpoints
# ---------------------------------------------------------------------------

@app.get("/pipelines", response_model=list[PipelineConfig])
async def list_pipelines(
    current_user: str = Depends(get_current_user),
) -> list[PipelineConfig]:
    """List all saved pipeline configs."""
    return pipeline_manager.list_all()


@app.post("/pipelines", response_model=PipelineConfig, status_code=201)
async def save_pipeline(
    config: PipelineConfig,
    current_user: str = Depends(get_current_user),
) -> PipelineConfig:
    """Save (create or overwrite) a pipeline config."""
    pipeline_manager.save(config)
    return config


@app.get("/pipelines/{pipeline_id}", response_model=PipelineConfig)
async def get_pipeline(
    pipeline_id: str,
    current_user: str = Depends(get_current_user),
) -> PipelineConfig:
    """Load a single pipeline config by id."""
    config = pipeline_manager.load(pipeline_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found.")
    return config


@app.delete("/pipelines/{pipeline_id}")
async def delete_pipeline(
    pipeline_id: str,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Delete a saved pipeline."""
    if not pipeline_manager.delete(pipeline_id):
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found.")
    return {"deleted": pipeline_id}


@app.post("/pipelines/run", response_model=PipelineRunResult)
async def run_pipeline_adhoc(
    body: PipelineRunRequest,
    current_user: str = Depends(get_current_user),
) -> PipelineRunResult:
    """Run an unsaved pipeline config directly (ad-hoc, no save)."""
    if body.pipeline is None:
        raise HTTPException(status_code=422, detail="'pipeline' field is required for ad-hoc run.")
    return await pipeline_manager.run(body.pipeline, body.input)


@app.post("/pipelines/{pipeline_id}/run", response_model=PipelineRunResult)
async def run_saved_pipeline(
    pipeline_id: str,
    body: PipelineRunRequest,
    current_user: str = Depends(get_current_user),
) -> PipelineRunResult:
    """Run a saved pipeline by id."""
    config = pipeline_manager.load(pipeline_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found.")
    return await pipeline_manager.run(config, body.input)


# ---------------------------------------------------------------------------
# Monitor endpoints
# ---------------------------------------------------------------------------

@app.get("/monitor/stats")
async def monitor_stats(
    current_user: str = Depends(get_current_user),
) -> dict:
    """Return aggregate run statistics for the current user."""
    return metrics.stats(username=current_user)


@app.get("/monitor/runs")
async def monitor_runs(
    limit: int = Query(50, ge=1, le=500),
    agent: str | None = Query(None),
    current_user: str = Depends(get_current_user),
) -> list[dict]:
    """Return recent run records for the current user, newest first."""
    runs = metrics.recent(limit=limit, username=current_user, agent_name=agent)
    return [r.to_dict() for r in runs]


@app.get("/monitor/runs/{run_id}")
async def monitor_run_detail(
    run_id: str,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Return full detail for a single run."""
    record = metrics.get(run_id)
    if record is None or record.username != current_user:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return record.to_dict()


# ---------------------------------------------------------------------------
# File upload endpoint
# ---------------------------------------------------------------------------

@app.post("/upload", response_model=FileUploadResult, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
) -> FileUploadResult:
    """Upload a file (PDF, CSV, image, text) and return extracted text context.

    The returned ``text`` field can be included as ``files`` in the WebSocket
    payload so the agent sees the file content as context.
    """
    if file.size and file.size > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 20 MB limit.")

    content = await file.read()
    info = extract_text(file.filename or "upload", content)
    return FileUploadResult(
        file_id=info["file_id"],
        filename=info["filename"],
        type=info["type"],
        mime=info["mime"],
        size=info["size"],
        text=info["text"],
        has_text=bool(info["text"]),
    )


# ---------------------------------------------------------------------------
# Schedule endpoints
# ---------------------------------------------------------------------------

@app.get("/schedules", response_model=list[ScheduleResponse])
async def list_schedules(
    current_user: str = Depends(get_current_user),
) -> list[ScheduleResponse]:
    """List all schedules owned by the current user."""
    return [ScheduleResponse(**s.to_dict()) for s in scheduler.list_all(current_user)]


@app.post("/schedules", response_model=ScheduleResponse, status_code=201)
async def create_schedule(
    body: CreateScheduleRequest,
    current_user: str = Depends(get_current_user),
) -> ScheduleResponse:
    """Create a new scheduled agent run."""
    import uuid as _uuid
    cfg = ScheduleConfig(
        id=str(_uuid.uuid4())[:8],
        name=body.name,
        agent_name=body.agent_name,
        input_message=body.input_message,
        username=current_user,
        trigger_type=body.trigger_type,
        interval_seconds=body.interval_seconds,
        cron=body.cron,
        enabled=body.enabled,
    )
    scheduler.add(cfg)
    return ScheduleResponse(**cfg.to_dict())


@app.get("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: str,
    current_user: str = Depends(get_current_user),
) -> ScheduleResponse:
    """Get a single schedule by id."""
    cfg = scheduler.get(schedule_id)
    if cfg is None or cfg.username != current_user:
        raise HTTPException(status_code=404, detail=f"Schedule '{schedule_id}' not found.")
    return ScheduleResponse(**cfg.to_dict())


@app.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Delete a schedule and stop its background task."""
    cfg = scheduler.get(schedule_id)
    if cfg is None or cfg.username != current_user:
        raise HTTPException(status_code=404, detail=f"Schedule '{schedule_id}' not found.")
    scheduler.remove(schedule_id)
    return {"deleted": schedule_id}


@app.post("/schedules/{schedule_id}/enable")
async def enable_schedule(
    schedule_id: str,
    current_user: str = Depends(get_current_user),
) -> ScheduleResponse:
    """Enable a paused schedule and restart its background task."""
    cfg = scheduler.get(schedule_id)
    if cfg is None or cfg.username != current_user:
        raise HTTPException(status_code=404, detail=f"Schedule '{schedule_id}' not found.")
    return ScheduleResponse(**scheduler.set_enabled(schedule_id, True).to_dict())


@app.post("/schedules/{schedule_id}/disable")
async def disable_schedule(
    schedule_id: str,
    current_user: str = Depends(get_current_user),
) -> ScheduleResponse:
    """Disable (pause) a schedule without deleting it."""
    cfg = scheduler.get(schedule_id)
    if cfg is None or cfg.username != current_user:
        raise HTTPException(status_code=404, detail=f"Schedule '{schedule_id}' not found.")
    return ScheduleResponse(**scheduler.set_enabled(schedule_id, False).to_dict())


@app.post("/schedules/{schedule_id}/run")
async def run_schedule_now(
    schedule_id: str,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Trigger a schedule immediately (manual run)."""
    cfg = scheduler.get(schedule_id)
    if cfg is None or cfg.username != current_user:
        raise HTTPException(status_code=404, detail=f"Schedule '{schedule_id}' not found.")
    result = await scheduler.trigger_now(schedule_id)
    return result


# ---------------------------------------------------------------------------
# Webhook trigger (no auth — protected by secret token)
# ---------------------------------------------------------------------------

@app.post("/webhook/{token}")
async def webhook_trigger(token: str) -> dict:
    """Trigger a schedule via its webhook token.

    No JWT required — the token acts as the shared secret.
    Returns HTTP 404 if the token is unknown (avoids oracle attacks).
    """
    cfg = scheduler.get_by_webhook_token(token)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Unknown webhook token.")
    result = await scheduler.trigger_now(cfg.id)
    return result

