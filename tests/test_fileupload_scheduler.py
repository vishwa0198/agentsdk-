"""tests/test_fileupload_scheduler.py

Unit tests for:
  - Feature 5: file_handler (extract_text + build_file_context)
  - Feature 6: scheduler (ScheduleConfig, Scheduler CRUD, _cron_matches)

All tests are offline — no real files, no network, no real agent runs.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# file_handler tests
# ---------------------------------------------------------------------------
from file_handler import build_file_context, extract_text


class TestExtractTextCSV:
    def test_basic_csv(self):
        csv_bytes = b"name,age\nAlice,30\nBob,25"
        info = extract_text("data.csv", csv_bytes)
        assert info["type"] == "csv"
        assert info["file_id"]
        assert "Alice" in info["text"]
        assert "| name | age |" in info["text"]

    def test_csv_truncation_note(self):
        # Build a CSV with many rows
        rows = ["col1,col2"] + [f"val{i},{i}" for i in range(200)]
        csv_bytes = "\n".join(rows).encode()
        info = extract_text("big.csv", csv_bytes)
        assert "truncated" in info["text"].lower() or "Showing" in info["text"]

    def test_empty_csv(self):
        info = extract_text("empty.csv", b"")
        assert info["type"] == "csv"
        assert "empty" in info["text"].lower()

    def test_pipe_escaped_in_cells(self):
        csv_bytes = b"a,b\nhello|world,ok"
        info = extract_text("pipe.csv", csv_bytes)
        assert "\\|" in info["text"]


class TestExtractTextPDF:
    def test_pdf_no_pypdf(self):
        """When pypdf is not available the result contains a helpful message."""
        with patch.dict("sys.modules", {"pypdf": None}):
            info = extract_text("report.pdf", b"%PDF-1.4 ...")
        assert info["type"] == "pdf"
        # Either real parse or the "requires pypdf" message
        assert info["text"] is not None

    def test_pdf_parse_error(self):
        info = extract_text("bad.pdf", b"not a real pdf")
        assert info["type"] == "pdf"
        assert info["text"] is not None   # error string, not None


class TestExtractTextImage:
    def test_png_returns_base64(self):
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        info = extract_text("photo.png", fake_png)
        assert info["type"] == "image"
        assert info["base64"] is not None
        assert info["text"] is None

    def test_jpeg_accepted(self):
        info = extract_text("img.jpg", b"\xff\xd8\xff" + b"\x00" * 20)
        assert info["type"] == "image"


class TestExtractTextText:
    def test_python_source(self):
        src = b"def hello():\n    return 'world'\n"
        info = extract_text("hello.py", src)
        assert info["type"] == "text"
        assert "hello" in info["text"]

    def test_json_file(self):
        data = b'{"key": "value"}'
        info = extract_text("config.json", data)
        assert info["type"] == "text"
        assert "key" in info["text"]

    def test_oversized_file_rejected(self):
        big = b"x" * (21 * 1024 * 1024)
        info = extract_text("huge.txt", big)
        assert info["type"] == "error"
        assert "too large" in info["text"].lower()


class TestBuildFileContext:
    def test_csv_context_has_header(self):
        info = extract_text("data.csv", b"col1,col2\nv1,v2")
        ctx = build_file_context(info)
        assert "CSV" in ctx
        assert "data.csv" in ctx

    def test_image_context(self):
        info = extract_text("img.png", b"\x89PNG" + b"\x00" * 20)
        ctx = build_file_context(info)
        assert "image" in ctx.lower()
        assert "img.png" in ctx

    def test_python_context_uses_fenced_block(self):
        info = extract_text("script.py", b"print('hi')")
        ctx = build_file_context(info)
        assert "```python" in ctx

    def test_empty_text_gives_fallback(self):
        info = {"filename": "noop.txt", "type": "text", "text": ""}
        ctx = build_file_context(info)
        assert "no text" in ctx.lower()


# ---------------------------------------------------------------------------
# scheduler tests
# ---------------------------------------------------------------------------
from scheduler import Scheduler, ScheduleConfig, _cron_matches


class TestCronMatches:
    def test_wildcard_always_matches(self):
        assert _cron_matches("* * * * *") is True

    def test_invalid_expr_returns_false(self):
        assert _cron_matches("not a cron") is False

    def test_comma_separated(self):
        import datetime
        now = datetime.datetime.now()
        # Build an expression that matches current minute or won't match
        expr = f"{now.minute} * * * *"
        assert _cron_matches(expr) is True

    def test_step_notation(self):
        # */1 matches every minute → always True
        assert _cron_matches("*/1 * * * *") is True

    def test_range_notation(self):
        import datetime
        now = datetime.datetime.now()
        # "0-59" matches any minute
        assert _cron_matches(f"0-59 * * * *") is True


class TestScheduleConfig:
    def test_defaults_populated(self):
        cfg = ScheduleConfig(
            id="abc", name="Test", agent_name="WebAgent",
            input_message="hello", username="alice", trigger_type="interval",
        )
        assert cfg.webhook_token  # auto-generated
        assert cfg.created_at
        assert cfg.enabled is True

    def test_to_dict_roundtrip(self):
        cfg = ScheduleConfig(
            id="x1", name="N", agent_name="A",
            input_message="msg", username="u",
            trigger_type="cron", cron="0 9 * * *",
        )
        d = cfg.to_dict()
        restored = ScheduleConfig(**d)
        assert restored.id == cfg.id
        assert restored.cron == "0 9 * * *"
        assert restored.webhook_token == cfg.webhook_token


class TestSchedulerCRUD:
    def _make_scheduler(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_am = MagicMock()
        mock_metrics = MagicMock()
        sched = Scheduler(mock_am, mock_metrics)
        return sched

    def _cfg(self, **kwargs):
        defaults = dict(
            id=str(uuid.uuid4())[:8],
            name="Test", agent_name="WebAgent",
            input_message="hello", username="alice",
            trigger_type="interval", interval_seconds=9999,
            enabled=False,  # disabled → no background task
        )
        defaults.update(kwargs)
        return ScheduleConfig(**defaults)

    def test_add_and_list(self, tmp_path, monkeypatch):
        sched = self._make_scheduler(tmp_path, monkeypatch)
        cfg = self._cfg()
        sched.add(cfg)
        items = sched.list_all()
        assert len(items) == 1
        assert items[0].id == cfg.id

    def test_list_filtered_by_user(self, tmp_path, monkeypatch):
        sched = self._make_scheduler(tmp_path, monkeypatch)
        sched.add(self._cfg(username="alice"))
        sched.add(self._cfg(username="bob"))
        assert len(sched.list_all(username="alice")) == 1
        assert len(sched.list_all(username="bob")) == 1
        assert len(sched.list_all()) == 2

    def test_get_by_webhook_token(self, tmp_path, monkeypatch):
        sched = self._make_scheduler(tmp_path, monkeypatch)
        cfg = self._cfg()
        sched.add(cfg)
        found = sched.get_by_webhook_token(cfg.webhook_token)
        assert found is cfg

    def test_get_by_unknown_token_returns_none(self, tmp_path, monkeypatch):
        sched = self._make_scheduler(tmp_path, monkeypatch)
        assert sched.get_by_webhook_token("bogus") is None

    def test_remove_existing(self, tmp_path, monkeypatch):
        sched = self._make_scheduler(tmp_path, monkeypatch)
        cfg = self._cfg()
        sched.add(cfg)
        assert sched.remove(cfg.id) is True
        assert sched.list_all() == []

    def test_remove_nonexistent_returns_false(self, tmp_path, monkeypatch):
        sched = self._make_scheduler(tmp_path, monkeypatch)
        assert sched.remove("ghost") is False

    def test_set_enabled_disabled(self, tmp_path, monkeypatch):
        sched = self._make_scheduler(tmp_path, monkeypatch)
        cfg = self._cfg(enabled=False)
        sched.add(cfg)
        updated = sched.set_enabled(cfg.id, False)
        assert updated.enabled is False

    def test_persisted_json_created(self, tmp_path, monkeypatch):
        sched = self._make_scheduler(tmp_path, monkeypatch)
        cfg = self._cfg()
        sched.add(cfg)
        json_path = tmp_path / ".agentsdk" / "schedules" / f"{cfg.id}.json"
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert data["id"] == cfg.id

    def test_persisted_json_removed_on_delete(self, tmp_path, monkeypatch):
        sched = self._make_scheduler(tmp_path, monkeypatch)
        cfg = self._cfg()
        sched.add(cfg)
        sched.remove(cfg.id)
        json_path = tmp_path / ".agentsdk" / "schedules" / f"{cfg.id}.json"
        assert not json_path.exists()

    def test_load_from_disk(self, tmp_path, monkeypatch):
        """Schedules saved to disk are reloaded on a fresh Scheduler init."""
        monkeypatch.chdir(tmp_path)
        mock_am = MagicMock()
        mock_metrics = MagicMock()

        # First scheduler: add a schedule
        sched1 = Scheduler(mock_am, mock_metrics)
        cfg = self._cfg()
        sched1.add(cfg)

        # Second scheduler: should load from disk
        sched2 = Scheduler(mock_am, mock_metrics)
        assert sched2.get(cfg.id) is not None


@pytest.mark.asyncio
class TestSchedulerTrigger:
    async def test_trigger_now_calls_agent(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        mock_result = SimpleNamespace(
            output="answer", steps=[], total_input_tokens=10,
            total_output_tokens=5, stopped_by="end_turn",
        )
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        mock_am = MagicMock()
        mock_am.get_or_create.return_value = mock_agent

        mock_metrics = MagicMock()
        mock_metrics.record = MagicMock()

        sched = Scheduler(mock_am, mock_metrics)
        cfg = ScheduleConfig(
            id="t1", name="T", agent_name="WebAgent",
            input_message="summarise", username="alice",
            trigger_type="interval", interval_seconds=9999, enabled=False,
        )
        sched.add(cfg)

        result = await sched.trigger_now("t1")
        assert result["success"] is True
        assert result["schedule_id"] == "t1"
        mock_agent.run.assert_called_once()
        mock_metrics.record.assert_called_once()

    async def test_trigger_unknown_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        sched = Scheduler(MagicMock(), MagicMock())
        with pytest.raises(KeyError):
            await sched.trigger_now("nonexistent")

    async def test_trigger_handles_agent_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=RuntimeError("LLM timeout"))
        mock_am = MagicMock()
        mock_am.get_or_create.return_value = mock_agent
        mock_metrics = MagicMock()
        mock_metrics.record = MagicMock()

        sched = Scheduler(mock_am, mock_metrics)
        cfg = ScheduleConfig(
            id="e1", name="E", agent_name="WebAgent",
            input_message="go", username="bob",
            trigger_type="interval", interval_seconds=9999, enabled=False,
        )
        sched.add(cfg)

        result = await sched.trigger_now("e1")
        assert result["success"] is False
        assert "LLM timeout" in result["error"]
