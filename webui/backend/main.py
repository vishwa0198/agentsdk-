"""webui/backend/main.py — FastAPI application with REST + WebSocket endpoints."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from agent_manager import AgentManager
from models import ChatRequest, ChatResponse, SessionInfo, StreamEvent

# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

manager = AgentManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the AgentManager once at startup."""
    yield


# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

app = FastAPI(
    title="agentsdk Web UI",
    description="Chat with agentsdk agents over REST and WebSocket.",
    version="0.1.2",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    return {"status": "ok", "version": "0.1.2"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Synchronous chat — run the full agent loop and return a complete result."""
    agent = manager.get_or_create(request.session_id, request.agent_name)
    result = await agent.run(request.message, session_id=request.session_id)
    return ChatResponse(
        session_id=request.session_id,
        output=result.output,
        steps=len(result.steps),
        input_tokens=result.total_input_tokens,
        output_tokens=result.total_output_tokens,
        stopped_by=result.stopped_by,
    )


@app.get("/sessions/{agent_name}", response_model=list[SessionInfo])
async def list_sessions(agent_name: str) -> list[SessionInfo]:
    """Return metadata for all persisted sessions of *agent_name*."""
    return await manager.list_sessions(agent_name)


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict:
    """Delete a session's checkpoint and vector data."""
    await manager.delete_session(session_id)
    return {"deleted": session_id}


# ---------------------------------------------------------------------------
# WebSocket streaming endpoint
# ---------------------------------------------------------------------------


@app.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str) -> None:
    """Stream agent events in real-time over WebSocket.

    Protocol:
        Client sends:  {"message": "...", "agent_name": "..."}
        Server emits one or more StreamEvent objects:
            {"type": "step",        "data": {"iteration": n, "thought": "..."}}
            {"type": "tool_call",   "data": {"name": "...", "arguments": {...}}}
            {"type": "tool_result", "data": {"name": "...", "result": "...", "is_error": false}}
            {"type": "final",       "data": {"output": "...", "steps": n, "tokens": {...}}}
            {"type": "error",       "data": {"message": "..."}}
    """
    await websocket.accept()

    try:
        payload = await websocket.receive_json()
        message: str = payload.get("message", "")
        agent_name: str = payload.get("agent_name", "WebAgent")

        if not message.strip():
            await websocket.send_json(
                StreamEvent(type="error", data={"message": "Empty message."}).model_dump()
            )
            return

        agent = manager.get_or_create(session_id, agent_name)

        # Wire up the step callback to forward every event to the client.
        async def _emit(event_type: str, data: dict) -> None:
            await websocket.send_json(
                StreamEvent(type=event_type, data=data).model_dump()
            )

        agent._step_callback = _emit

        try:
            await agent.run(message, session_id=session_id)
        except Exception as exc:  # noqa: BLE001
            await websocket.send_json(
                StreamEvent(type="error", data={"message": str(exc)}).model_dump()
            )
        finally:
            agent._step_callback = None

    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        try:
            await websocket.send_json(
                StreamEvent(type="error", data={"message": str(exc)}).model_dump()
            )
        except Exception:
            pass
