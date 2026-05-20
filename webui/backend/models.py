"""webui/backend/models.py — Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


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


# ---------------------------------------------------------------------------
# Auth models
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserInfo(BaseModel):
    username: str
    created_at: datetime
