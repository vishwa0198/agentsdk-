"""webui/backend/metrics_store.py

In-memory store for agent run metrics.

Keeps a ring-buffer of the last MAX_RUNS completed runs so the monitoring
dashboard can display recent activity without touching the filesystem.  The
store is populated by the WebSocket handler in main.py immediately after
every ``agent.run()`` call completes.

Data is intentionally not persisted to disk — it resets on restart.
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean, quantiles
from typing import Any


MAX_RUNS = 500   # ring-buffer size


# ---------------------------------------------------------------------------
# RunRecord — one completed agent run
# ---------------------------------------------------------------------------

@dataclass
class RunRecord:
    """All observable metrics for a single completed ``agent.run()`` call."""

    run_id: str
    username: str
    session_id: str      # user-facing id (no username__ prefix)
    agent_name: str

    started_at: str      # ISO-8601 UTC
    finished_at: str     # ISO-8601 UTC
    latency_ms: int

    input_tokens: int
    output_tokens: int
    iterations: int

    tool_calls: list[dict[str, Any]]   # [{"name": "...", "arguments": {...}}]
    stopped_by: str      # "end_turn" | "max_iterations" | "error"
    success: bool
    error: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "username": self.username,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "iterations": self.iterations,
            "tool_calls": self.tool_calls,
            "tool_call_count": len(self.tool_calls),
            "stopped_by": self.stopped_by,
            "success": self.success,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# MetricsStore
# ---------------------------------------------------------------------------

class MetricsStore:
    """Thread-safe (single-loop) ring-buffer for RunRecord entries.

    Designed for FastAPI's single-worker asyncio model — no locking needed
    since all mutations happen in the same event loop.
    """

    def __init__(self, maxlen: int = MAX_RUNS) -> None:
        self._runs: deque[RunRecord] = deque(maxlen=maxlen)
        # run_id → RunRecord for O(1) lookup
        self._by_id: dict[str, RunRecord] = {}

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(self, record: RunRecord) -> None:
        """Append *record* to the ring buffer."""
        if len(self._runs) == self._runs.maxlen:
            # Evict the oldest record from the lookup index too.
            oldest = self._runs[0]
            self._by_id.pop(oldest.run_id, None)
        self._runs.append(record)
        self._by_id[record.run_id] = record

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, run_id: str) -> RunRecord | None:
        return self._by_id.get(run_id)

    def recent(
        self,
        limit: int = 50,
        username: str | None = None,
        agent_name: str | None = None,
    ) -> list[RunRecord]:
        """Return up to *limit* most-recent records, optionally filtered."""
        runs = list(reversed(self._runs))   # newest first
        if username:
            runs = [r for r in runs if r.username == username]
        if agent_name:
            runs = [r for r in runs if r.agent_name == agent_name]
        return runs[:limit]

    def stats(self, username: str | None = None) -> dict[str, Any]:
        """Return aggregate statistics across all (or filtered) runs."""
        runs = list(self._runs)
        if username:
            runs = [r for r in runs if r.username == username]

        if not runs:
            return _empty_stats()

        now = datetime.now(timezone.utc)
        latencies = [r.latency_ms for r in runs]
        total_input = sum(r.input_tokens for r in runs)
        total_output = sum(r.output_tokens for r in runs)
        success_count = sum(1 for r in runs if r.success)
        tool_calls_flat = [tc["name"] for r in runs for tc in r.tool_calls]

        # top tools
        tool_freq: dict[str, int] = {}
        for name in tool_calls_flat:
            tool_freq[name] = tool_freq.get(name, 0) + 1
        top_tools = sorted(tool_freq.items(), key=lambda x: -x[1])[:8]

        # p95 latency
        p95 = int(quantiles(latencies, n=20)[18]) if len(latencies) >= 2 else latencies[0]

        # runs in last hour / 24h
        def _age_sec(r: RunRecord) -> float:
            try:
                t = datetime.fromisoformat(r.finished_at)
                return (now - t).total_seconds()
            except Exception:
                return 9999

        runs_last_hour = sum(1 for r in runs if _age_sec(r) <= 3600)
        runs_last_24h = sum(1 for r in runs if _age_sec(r) <= 86400)

        # active sessions — sessions with a run started in last 5 min
        active = {r.session_id for r in runs if _age_sec(r) <= 300}

        return {
            "total_runs": len(runs),
            "success_runs": success_count,
            "error_runs": len(runs) - success_count,
            "success_rate": round(success_count / len(runs) * 100, 1),
            "avg_latency_ms": int(mean(latencies)),
            "p95_latency_ms": p95,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_tool_calls": len(tool_calls_flat),
            "top_tools": [{"name": n, "count": c} for n, c in top_tools],
            "runs_last_hour": runs_last_hour,
            "runs_last_24h": runs_last_24h,
            "active_sessions": len(active),
        }


def _empty_stats() -> dict[str, Any]:
    return {
        "total_runs": 0, "success_runs": 0, "error_runs": 0, "success_rate": 0.0,
        "avg_latency_ms": 0, "p95_latency_ms": 0,
        "total_input_tokens": 0, "total_output_tokens": 0, "total_tokens": 0,
        "total_tool_calls": 0, "top_tools": [],
        "runs_last_hour": 0, "runs_last_24h": 0, "active_sessions": 0,
    }


# ---------------------------------------------------------------------------
# Helpers used by main.py
# ---------------------------------------------------------------------------

def build_record(
    *,
    username: str,
    session_id: str,
    agent_name: str,
    started_at: float,          # time.monotonic() start
    started_wall: datetime,     # wall-clock start
    result: Any,                # AgentResult
    error: str | None = None,
) -> RunRecord:
    """Construct a RunRecord from an AgentResult."""
    finished = datetime.now(timezone.utc)
    latency_ms = int((time.monotonic() - started_at) * 1000)

    tool_calls: list[dict] = []
    if result is not None:
        for step in result.steps:
            for tc in step.tool_calls:
                tool_calls.append({
                    "name": tc.name,
                    "arguments": tc.arguments,
                    "iteration": step.iteration,
                })

    return RunRecord(
        run_id=str(uuid.uuid4())[:12],
        username=username,
        session_id=session_id,
        agent_name=agent_name,
        started_at=started_wall.isoformat(),
        finished_at=finished.isoformat(),
        latency_ms=latency_ms,
        input_tokens=result.total_input_tokens if result else 0,
        output_tokens=result.total_output_tokens if result else 0,
        iterations=len(result.steps) if result else 0,
        tool_calls=tool_calls,
        stopped_by=result.stopped_by if result else "error",
        success=result is not None and result.stopped_by != "error",
        error=error,
    )
