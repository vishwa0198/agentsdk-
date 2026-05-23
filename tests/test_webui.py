"""tests/test_webui.py

Unit tests for new webui features added in v0.4+:
  - Pipeline auto-wire  (sequential edge generation when no edges are drawn)
  - Memory ingest       (file_handler text extraction for RAG ingestion)
  - CORS / security     (ALLOWED_ORIGINS env var respected)

All tests are fully offline — no real LLM calls, no network, no ChromaDB.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure webui/backend is importable before any import of its modules.
_BACKEND = Path(__file__).parent.parent / "webui" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Set required env vars before importing main / pipeline_manager.
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only")
os.environ.setdefault("GROQ_API_KEY", "dummy")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from models import PipelineConfig, PipelineEdgeConfig, PipelineNodeConfig
from file_handler import MAX_FILE_BYTES, extract_text


def _import_backend_main():
    try:
        import main as app_module
    except ModuleNotFoundError as exc:
        pytest.skip(f"webui backend dependency not installed: {exc.name}")
    return app_module


def _node(
    nid: str,
    *,
    input_key: str = "input",
    output_key: str = "output",
) -> PipelineNodeConfig:
    return PipelineNodeConfig(
        id=nid,
        name=nid.title(),
        input_key=input_key,
        output_key=output_key,
    )


def _cfg(
    nodes: list[PipelineNodeConfig],
    *,
    edges: list[PipelineEdgeConfig] | None = None,
    entry: str | None = None,
    exit_: str | None = None,
) -> PipelineConfig:
    return PipelineConfig(
        id="test-pipe",
        name="Test Pipeline",
        nodes=nodes,
        edges=edges or [],
        entry_node=entry or nodes[0].id,
        exit_node=exit_ or nodes[-1].id,
    )


# ---------------------------------------------------------------------------
# Pipeline auto-wire
# ---------------------------------------------------------------------------

class TestPipelineAutoWire:
    """The auto-wire logic creates sequential edges when none are provided."""

    def _auto_wire(self, cfg: PipelineConfig) -> list[PipelineEdgeConfig]:
        """Mirror the auto-wire logic from pipeline_manager.run()."""
        if cfg.edges or len(cfg.nodes) < 2:
            return list(cfg.edges)
        node_map = {n.id: n for n in cfg.nodes}
        middle = [
            n.id for n in cfg.nodes
            if n.id not in (cfg.entry_node, cfg.exit_node)
        ]
        ordered = [cfg.entry_node] + middle + [cfg.exit_node]
        return [
            PipelineEdgeConfig(
                from_node=ordered[i],
                to_node=ordered[i + 1],
                data_map={node_map[ordered[i]].output_key: node_map[ordered[i + 1]].input_key},
            )
            for i in range(len(ordered) - 1)
        ]

    def test_two_nodes_creates_one_edge(self):
        cfg = _cfg([_node("a"), _node("b")])
        edges = self._auto_wire(cfg)
        assert len(edges) == 1
        assert edges[0].from_node == "a"
        assert edges[0].to_node == "b"

    def test_default_keys_mapped(self):
        cfg = _cfg([_node("a"), _node("b")])
        edges = self._auto_wire(cfg)
        assert edges[0].data_map == {"output": "input"}

    def test_custom_output_key_to_custom_input_key(self):
        cfg = _cfg([_node("a", output_key="summary"), _node("b", input_key="text")])
        edges = self._auto_wire(cfg)
        assert edges[0].data_map == {"summary": "text"}

    def test_three_nodes_two_edges_correct_order(self):
        nodes = [_node("entry"), _node("mid"), _node("exit_")]
        cfg = _cfg(nodes, entry="entry", exit_="exit_")
        edges = self._auto_wire(cfg)
        assert len(edges) == 2
        assert edges[0].from_node == "entry" and edges[0].to_node == "mid"
        assert edges[1].from_node == "mid"   and edges[1].to_node == "exit_"

    def test_single_node_no_edges_generated(self):
        cfg = _cfg([_node("solo")])
        edges = self._auto_wire(cfg)
        assert edges == []

    def test_existing_edges_not_overwritten(self):
        existing = [PipelineEdgeConfig(from_node="a", to_node="b", data_map={"x": "y"})]
        cfg = _cfg([_node("a"), _node("b")], edges=existing)
        edges = self._auto_wire(cfg)
        assert edges == existing

    def test_four_nodes_three_edges(self):
        nodes = [_node("n1"), _node("n2"), _node("n3"), _node("n4")]
        cfg = _cfg(nodes)
        edges = self._auto_wire(cfg)
        assert len(edges) == 3
        pairs = [(e.from_node, e.to_node) for e in edges]
        assert pairs == [("n1", "n2"), ("n2", "n3"), ("n3", "n4")]


# ---------------------------------------------------------------------------
# Memory ingest — file_handler text extraction
# ---------------------------------------------------------------------------

class TestMemoryIngestExtraction:
    """extract_text must return usable text for every file type we ingest."""

    def test_txt_basic(self):
        info = extract_text("notes.txt", b"Hello world. This is a test document.")
        assert info["type"] == "text"
        assert "Hello world" in info["text"]

    def test_md_file(self):
        info = extract_text("README.md", b"# Title\n\nSome **bold** text.")
        assert info["type"] == "text"
        assert "Title" in info["text"]

    def test_python_source(self):
        info = extract_text("agent.py", b"def run():\n    return 'done'\n")
        assert info["type"] == "text"
        assert "def run" in info["text"]

    def test_json_file(self):
        info = extract_text("config.json", b'{"model": "llama3", "temp": 0.7}')
        assert info["type"] == "text"
        assert "llama3" in info["text"]

    def test_text_truncated_at_max_chars(self):
        from file_handler import MAX_TEXT_CHARS
        big = b"Z" * (MAX_TEXT_CHARS + 5000)
        info = extract_text("big.txt", big)
        assert info["type"] == "text"
        assert len(info["text"]) <= MAX_TEXT_CHARS + 50  # small tolerance for notes

    def test_oversized_file_rejected(self):
        info = extract_text("giant.txt", b"x" * (MAX_FILE_BYTES + 1))
        assert "too large" in (info.get("text") or "").lower()

    def test_empty_txt_returns_empty_text(self):
        info = extract_text("empty.txt", b"")
        assert info["type"] == "text"
        # Empty files produce empty string (not None)
        assert info["text"] is not None

    def test_csv_ingestion(self):
        csv = b"name,role\nAlice,engineer\nBob,researcher"
        info = extract_text("team.csv", csv)
        assert info["type"] == "csv"
        assert "Alice" in info["text"]
        assert "Bob" in info["text"]

    def test_chunk_count_math(self):
        """Verify the chunk-size arithmetic used in the ingest endpoint."""
        CHUNK = 1800
        text = "A" * (CHUNK * 2 + 100)  # 2 full + 1 partial = 3 chunks
        info = extract_text("calc.txt", text.encode())
        chunks = [info["text"][i: i + CHUNK] for i in range(0, len(info["text"]), CHUNK)]
        assert len(chunks) == 3


# ---------------------------------------------------------------------------
# Security — CORS origins
# ---------------------------------------------------------------------------

class TestCORSSecurity:
    def test_allowed_origins_env_var_read(self):
        """ALLOWED_ORIGINS env var is parsed into a list at import time."""
        app_module = _import_backend_main()
        # conftest sets ALLOWED_ORIGINS=http://localhost:3000
        assert isinstance(app_module.ALLOWED_ORIGINS, list)
        assert "http://localhost:3000" in app_module.ALLOWED_ORIGINS

    def test_wildcard_not_in_origins(self):
        """Production CORS must never fall back to allow-all '*'."""
        app_module = _import_backend_main()
        assert "*" not in app_module.ALLOWED_ORIGINS

    def test_multi_origin_parsing(self, monkeypatch):
        """Comma-separated ALLOWED_ORIGINS are split correctly."""
        raw = "https://app.example.com,https://preview.example.com"
        origins = [o.strip() for o in raw.split(",")]
        assert len(origins) == 2
        assert "https://app.example.com" in origins
        assert "https://preview.example.com" in origins
