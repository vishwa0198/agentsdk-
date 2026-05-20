"""webui/backend/main.py — FastAPI application with REST + WebSocket endpoints."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm

from agent_manager import AgentManager
from auth import create_access_token, decode_token, get_current_user, user_store
from models import (
    ChatRequest,
    ChatResponse,
    RegisterRequest,
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
    return {"status": "ok", "version": "0.2.0"}


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest) -> dict:
    try:
        user_store.add_user(body.username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "registered"}


@app.post("/auth/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
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
    session_key = f"{current_user}:{request.session_id}"
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
    prefix = f"{current_user}:"
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
    session_key = f"{current_user}:{session_id}"
    await manager.delete_session(session_key)
    return {"deleted": session_id}


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

    session_key = f"{username}:{session_id}"

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

        agent = manager.get_or_create(session_key, agent_name)

        # Wire up the step callback to forward every event to the client.
        async def _emit(event_type: str, data: dict) -> None:
            await websocket.send_json(
                StreamEvent(type=event_type, data=data).model_dump()
            )

        agent._step_callback = _emit

        try:
            result = await agent.run(message, session_id=session_key)
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

    return {"deleted": org_id}

