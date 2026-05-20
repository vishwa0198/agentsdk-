"""webui/backend/models.py — Pydantic request/response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: str
    message: str
    agent_name: str = "WebAgent"


class ChatResponse(BaseModel):
    session_id: str
    output: str
    steps: int
    input_tokens: int
    output_tokens: int
    stopped_by: str


class StreamEvent(BaseModel):
    type: str  # "step" | "tool_call" | "tool_result" | "final" | "error"
    data: dict[str, Any]


class SessionInfo(BaseModel):
    session_id: str
    agent_name: str
    message_count: int
    updated_at: str
