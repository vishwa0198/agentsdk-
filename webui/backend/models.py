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


# ---------------------------------------------------------------------------
# MCP models
# ---------------------------------------------------------------------------

class AddMCPServerRequest(BaseModel):
    """Request body for POST /mcp/servers."""
    name: str
    transport: str          # "stdio" | "sse" | "http"
    # stdio
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    # sse / http
    url: str | None = None


# ---------------------------------------------------------------------------
# Pipeline models
# ---------------------------------------------------------------------------

class PipelineNodeConfig(BaseModel):
    """Configuration for one agent node in a pipeline."""
    id: str
    name: str
    system_prompt: str = "You are a helpful assistant."
    model: str = "llama-3.1-8b-instant"
    max_iterations: int = 5
    input_key: str = "input"
    output_key: str = "output"
    position: dict[str, float] = {}   # {x, y} — stored for the canvas only


class PipelineEdgeConfig(BaseModel):
    """A directed connection between two nodes."""
    from_node: str
    to_node: str
    data_map: dict[str, str] = {}     # {upstream_key: downstream_key}


class PipelineConfig(BaseModel):
    """Full pipeline definition — nodes + edges + entry/exit."""
    id: str
    name: str
    nodes: list[PipelineNodeConfig] = []
    edges: list[PipelineEdgeConfig] = []
    entry_node: str | None = None
    exit_node: str | None = None


class PipelineRunRequest(BaseModel):
    """Request body for POST /pipelines/run (ad-hoc) or POST /pipelines/{id}/run."""
    pipeline: PipelineConfig | None = None   # omit to run a saved pipeline
    input: str = ""


class PipelineNodeResult(BaseModel):
    node_id: str
    name: str
    output: str
    success: bool
    error: str | None = None


class PipelineRunResult(BaseModel):
    success: bool
    final_output: str | None = None
    node_results: list[PipelineNodeResult] = []
    error: str | None = None


# ---------------------------------------------------------------------------
# File upload models
# ---------------------------------------------------------------------------

class FileUploadResult(BaseModel):
    """Response from POST /upload."""
    file_id: str
    filename: str
    type: str           # "pdf" | "csv" | "image" | "text" | "error"
    mime: str
    size: int
    text: str | None = None    # extracted text (omitted for images)
    has_text: bool = True


# ---------------------------------------------------------------------------
# Schedule models
# ---------------------------------------------------------------------------

class CreateScheduleRequest(BaseModel):
    name: str
    agent_name: str = "WebAgent"
    input_message: str
    trigger_type: str = "interval"   # "interval" | "cron"
    interval_seconds: int = 3600
    cron: str = "0 * * * *"
    enabled: bool = True


class ScheduleResponse(BaseModel):
    id: str
    name: str
    agent_name: str
    input_message: str
    username: str
    trigger_type: str
    interval_seconds: int
    cron: str
    enabled: bool
    webhook_token: str
    created_at: str
    last_run_at: str | None = None
    last_run_ok: bool | None = None
    last_output: str | None = None
