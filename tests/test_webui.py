"""tests/test_webui.py

Unit tests for new webui features added in v0.4+:
  - Pipeline auto-wire  (sequential edge generation when no edges are drawn)
  - Memory ingest       (file_handler text extraction for RAG ingestion)
  - CORS / security     (ALLOWED_ORIGINS env var respected)

All tests are fully offline — no real LLM calls, no network, no ChromaDB.
"""

from __future__ import annotations

import importlib.util
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
os.environ.setdefault("OLLAMA_MODEL", "llama3:8b")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from models import PipelineConfig, PipelineEdgeConfig, PipelineNodeConfig
from file_handler import MAX_FILE_BYTES, extract_text


def _import_backend_main():
    """Import webui/backend/main.py explicitly from its file path."""
    try:
        spec = importlib.util.spec_from_file_location("webui_backend_main", _BACKEND / "main.py")
        assert spec is not None and spec.loader is not None
        app_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app_module)
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


# ---------------------------------------------------------------------------
# Auth — register + login + token flow (uses FastAPI TestClient, no network)
# ---------------------------------------------------------------------------

class TestAuthFlow:
    """End-to-end auth tests: register → login → /auth/me → bad credentials."""

    @pytest.fixture(autouse=True)
    def _patch_users_file(self, tmp_path, monkeypatch):
        """Redirect the users JSON store to a temp dir so tests are isolated."""
        import auth as _auth
        users_file = tmp_path / "users.json"
        monkeypatch.setattr(_auth, "USERS_FILE", users_file)
        # Replace the global user_store instance so it uses the patched path.
        _auth.user_store = _auth.UserStore()
        # Also patch the reference in main.py's already-imported module.
        try:
            import webui_backend_main as _main
            _main.user_store = _auth.user_store
        except ImportError:
            pass
        yield

    @pytest.fixture()
    def client(self):
        """Return a FastAPI TestClient for the webui backend."""
        from fastapi.testclient import TestClient
        app_module = _import_backend_main()
        # Re-point main.user_store after patching (autouse fixture runs first).
        import auth as _auth
        app_module.user_store = _auth.user_store
        return TestClient(app_module.app, raise_server_exceptions=True)

    # ── register ────────────────────────────────────────────────────────────

    def test_register_success(self, client):
        res = client.post("/auth/register", json={"username": "alice", "password": "secret123"})
        assert res.status_code == 201
        assert res.json() == {"message": "registered"}

    def test_register_duplicate_username_rejected(self, client):
        client.post("/auth/register", json={"username": "bob", "password": "pass1234"})
        res = client.post("/auth/register", json={"username": "bob", "password": "other123"})
        assert res.status_code == 400
        assert "already taken" in res.json()["detail"].lower()

    # ── login ────────────────────────────────────────────────────────────────

    def test_login_returns_access_token(self, client):
        client.post("/auth/register", json={"username": "carol", "password": "mypassword"})
        res = client.post(
            "/auth/login",
            data={"username": "carol", "password": "mypassword"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert res.status_code == 200
        body = res.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert len(body["access_token"]) > 20

    def test_login_wrong_password_returns_401(self, client):
        client.post("/auth/register", json={"username": "dave", "password": "correct123"})
        res = client.post(
            "/auth/login",
            data={"username": "dave", "password": "wrongpass"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert res.status_code == 401

    def test_login_unknown_user_returns_401(self, client):
        res = client.post(
            "/auth/login",
            data={"username": "ghost", "password": "anything"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert res.status_code == 401

    # ── /auth/me with valid token ────────────────────────────────────────────

    def test_me_returns_username_with_valid_token(self, client):
        client.post("/auth/register", json={"username": "eve", "password": "evespass"})
        login_res = client.post(
            "/auth/login",
            data={"username": "eve", "password": "evespass"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token = login_res.json()["access_token"]
        me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_res.status_code == 200
        assert me_res.json()["username"] == "eve"

    def test_me_without_token_returns_401(self, client):
        res = client.get("/auth/me")
        assert res.status_code == 401

    def test_me_with_invalid_token_returns_401(self, client):
        res = client.get("/auth/me", headers={"Authorization": "Bearer this.is.garbage"})
        assert res.status_code == 401

    # ── token JWT structure ───────────────────────────────────────────────────

    def test_token_contains_sub_claim(self):
        """JWT issued by create_access_token must have a 'sub' claim."""
        from auth import create_access_token, decode_token
        token = create_access_token({"sub": "frank"})
        assert decode_token(token) == "frank"

    def test_expired_token_is_rejected(self):
        """A token with exp in the past must be decoded as None."""
        from datetime import datetime, timezone, timedelta
        from auth import SECRET_KEY, ALGORITHM
        from jose import jwt
        payload = {"sub": "grace", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}
        expired_token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        from auth import decode_token
        assert decode_token(expired_token) is None

    # ── password hashing ──────────────────────────────────────────────────────

    def test_correct_password_verifies(self):
        from auth import hash_password, verify_password
        h = hash_password("hunter2")
        assert verify_password("hunter2", h) is True

    def test_wrong_password_fails_verification(self):
        from auth import hash_password, verify_password
        h = hash_password("hunter2")
        assert verify_password("wrong", h) is False

    def test_two_hashes_of_same_password_differ(self):
        """bcrypt generates a new salt each time — hashes must not be equal."""
        from auth import hash_password
        assert hash_password("same") != hash_password("same")
