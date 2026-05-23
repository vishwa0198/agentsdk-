"""tests/test_monitor.py

Unit tests for MetricsStore and the build_record helper.
No network, no real agents — all offline.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from metrics_store import MetricsStore, RunRecord, build_record, _empty_stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record(
    username: str = "alice",
    session_id: str = "sess-1",
    agent_name: str = "WebAgent",
    latency_ms: int = 500,
    input_tokens: int = 100,
    output_tokens: int = 50,
    iterations: int = 2,
    tool_calls: list | None = None,
    stopped_by: str = "end_turn",
    success: bool = True,
    error: str | None = None,
) -> RunRecord:
    now = datetime.now(timezone.utc).isoformat()
    return RunRecord(
        run_id=str(uuid.uuid4()),
        username=username,
        session_id=session_id,
        agent_name=agent_name,
        started_at=now,
        finished_at=now,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        iterations=iterations,
        tool_calls=tool_calls or [],
        stopped_by=stopped_by,
        success=success,
        error=error,
    )


# ---------------------------------------------------------------------------
# RunRecord
# ---------------------------------------------------------------------------

class TestRunRecord:
    def test_total_tokens(self):
        r = _record(input_tokens=100, output_tokens=50)
        assert r.total_tokens == 150

    def test_to_dict_keys(self):
        r = _record()
        d = r.to_dict()
        assert "run_id" in d
        assert "latency_ms" in d
        assert "total_tokens" in d
        assert "tool_call_count" in d

    def test_to_dict_tool_call_count(self):
        r = _record(tool_calls=[{"name": "http_request", "arguments": {}}])
        assert r.to_dict()["tool_call_count"] == 1


# ---------------------------------------------------------------------------
# MetricsStore — basic CRUD
# ---------------------------------------------------------------------------

class TestMetricsStore:
    def test_empty_store(self):
        store = MetricsStore()
        assert store.recent() == []
        assert store.get("nonexistent") is None

    def test_record_and_get(self):
        store = MetricsStore()
        r = _record()
        store.record(r)
        assert store.get(r.run_id) is r

    def test_recent_newest_first(self):
        store = MetricsStore()
        r1 = _record(session_id="a"); store.record(r1)
        r2 = _record(session_id="b"); store.record(r2)
        r3 = _record(session_id="c"); store.record(r3)
        recent = store.recent()
        assert [r.session_id for r in recent] == ["c", "b", "a"]

    def test_recent_limit(self):
        store = MetricsStore()
        for i in range(10):
            store.record(_record(session_id=str(i)))
        assert len(store.recent(limit=3)) == 3

    def test_recent_filter_username(self):
        store = MetricsStore()
        store.record(_record(username="alice"))
        store.record(_record(username="bob"))
        store.record(_record(username="alice"))
        assert len(store.recent(username="alice")) == 2
        assert len(store.recent(username="bob")) == 1

    def test_recent_filter_agent(self):
        store = MetricsStore()
        store.record(_record(agent_name="ResearchAgent"))
        store.record(_record(agent_name="WebAgent"))
        assert len(store.recent(agent_name="ResearchAgent")) == 1

    def test_ring_buffer_evicts_oldest(self):
        store = MetricsStore(maxlen=3)
        ids = []
        for i in range(5):
            r = _record(session_id=str(i)); store.record(r); ids.append(r.run_id)
        # Only the last 3 should remain
        assert store.get(ids[0]) is None   # evicted
        assert store.get(ids[1]) is None   # evicted
        assert store.get(ids[2]) is not None
        assert store.get(ids[3]) is not None
        assert store.get(ids[4]) is not None

    def test_ring_buffer_lookup_index_stays_consistent(self):
        store = MetricsStore(maxlen=2)
        r1 = _record(); store.record(r1)
        r2 = _record(); store.record(r2)
        r3 = _record(); store.record(r3)
        # r1 should be gone from the index
        assert store.get(r1.run_id) is None
        assert store.get(r2.run_id) is not None
        assert store.get(r3.run_id) is not None


# ---------------------------------------------------------------------------
# MetricsStore — stats
# ---------------------------------------------------------------------------

class TestMetricsStoreStats:
    def test_empty_stats(self):
        store = MetricsStore()
        s = store.stats()
        assert s["total_runs"] == 0
        assert s["success_rate"] == 0.0

    def test_success_rate_calculation(self):
        store = MetricsStore()
        store.record(_record(success=True))
        store.record(_record(success=True))
        store.record(_record(success=False, stopped_by="error"))
        s = store.stats()
        assert s["total_runs"] == 3
        assert s["success_runs"] == 2
        assert s["error_runs"] == 1
        assert s["success_rate"] == pytest.approx(66.7, abs=0.2)

    def test_token_totals(self):
        store = MetricsStore()
        store.record(_record(input_tokens=100, output_tokens=50))
        store.record(_record(input_tokens=200, output_tokens=100))
        s = store.stats()
        assert s["total_input_tokens"] == 300
        assert s["total_output_tokens"] == 150
        assert s["total_tokens"] == 450

    def test_avg_latency(self):
        store = MetricsStore()
        store.record(_record(latency_ms=200))
        store.record(_record(latency_ms=400))
        s = store.stats()
        assert s["avg_latency_ms"] == 300

    def test_top_tools_sorted_by_frequency(self):
        store = MetricsStore()
        store.record(_record(tool_calls=[
            {"name": "http_request"}, {"name": "http_request"}, {"name": "read_file"}
        ]))
        store.record(_record(tool_calls=[{"name": "http_request"}]))
        s = store.stats()
        assert s["top_tools"][0]["name"] == "http_request"
        assert s["top_tools"][0]["count"] == 3

    def test_total_tool_calls(self):
        store = MetricsStore()
        store.record(_record(tool_calls=[{"name": "a"}, {"name": "b"}]))
        store.record(_record(tool_calls=[{"name": "c"}]))
        s = store.stats()
        assert s["total_tool_calls"] == 3

    def test_stats_filtered_by_username(self):
        store = MetricsStore()
        store.record(_record(username="alice", input_tokens=100))
        store.record(_record(username="bob", input_tokens=999))
        alice_stats = store.stats(username="alice")
        assert alice_stats["total_input_tokens"] == 100
        assert alice_stats["total_runs"] == 1

    def test_active_sessions(self):
        """A session that ran less than 5 min ago should appear in active_sessions."""
        store = MetricsStore()
        store.record(_record(session_id="recent"))
        s = store.stats()
        assert s["active_sessions"] == 1


# ---------------------------------------------------------------------------
# build_record helper
# ---------------------------------------------------------------------------

def _make_agent_result(
    input_tokens=20, output_tokens=10,
    stopped_by="end_turn",
    tool_calls_per_step=None,
):
    """Fake AgentResult with the fields build_record uses."""
    from agentsdk.messages import ToolCall

    steps = []
    for i, tc_names in enumerate(tool_calls_per_step or []):
        tcs = [ToolCall(id=f"id{j}", name=n, arguments={}) for j, n in enumerate(tc_names)]
        step = SimpleNamespace(iteration=i + 1, tool_calls=tcs)
        steps.append(step)

    return SimpleNamespace(
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
        stopped_by=stopped_by,
        steps=steps,
    )


class TestBuildRecord:
    def test_basic_fields(self):
        started = time.monotonic()
        wall = datetime.now(timezone.utc)
        result = _make_agent_result()
        rec = build_record(
            username="alice", session_id="s1", agent_name="WebAgent",
            started_at=started, started_wall=wall, result=result,
        )
        assert rec.username == "alice"
        assert rec.session_id == "s1"
        assert rec.agent_name == "WebAgent"
        assert rec.input_tokens == 20
        assert rec.output_tokens == 10
        assert rec.success is True
        assert rec.error is None
        assert rec.latency_ms >= 0

    def test_tool_calls_extracted(self):
        started = time.monotonic()
        wall = datetime.now(timezone.utc)
        result = _make_agent_result(tool_calls_per_step=[["read_file", "write_file"], ["http_request"]])
        rec = build_record(
            username="u", session_id="s", agent_name="A",
            started_at=started, started_wall=wall, result=result,
        )
        assert len(rec.tool_calls) == 3
        names = {tc["name"] for tc in rec.tool_calls}
        assert names == {"read_file", "write_file", "http_request"}

    def test_error_result(self):
        started = time.monotonic()
        wall = datetime.now(timezone.utc)
        rec = build_record(
            username="u", session_id="s", agent_name="A",
            started_at=started, started_wall=wall,
            result=None, error="connection refused",
        )
        assert rec.success is False
        assert rec.error == "connection refused"
        assert rec.stopped_by == "error"

    def test_stopped_by_max_iterations(self):
        started = time.monotonic()
        wall = datetime.now(timezone.utc)
        result = _make_agent_result(stopped_by="max_iterations")
        rec = build_record(
            username="u", session_id="s", agent_name="A",
            started_at=started, started_wall=wall, result=result,
        )
        assert rec.stopped_by == "max_iterations"
        assert rec.success is True   # not an error, just hit limit
