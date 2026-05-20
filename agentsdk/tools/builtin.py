"""agentsdk/tools/builtin.py

Ready-made tool bundle for common agent capabilities.

Quick start::

    from agentsdk.tools.builtin import DEFAULT_TOOLS
    agent = Agent(config=cfg, llm=llm, registry=DEFAULT_TOOLS)

All tools are safe to register together; individual tools can also be
imported and registered selectively.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
import httpx

from agentsdk.messages import HumanMessage
from agentsdk.tools.base import tool
from agentsdk.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# 1. http_request
# ---------------------------------------------------------------------------


@tool
async def http_request(url: str, method: str, body: str) -> str:
    """Make an HTTP GET or POST request and return the response body (max 3000 chars).

    method must be GET or POST. For POST, body is sent as raw JSON string.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if method.upper() == "POST":
                response = await client.post(
                    url,
                    content=body,
                    headers={"Content-Type": "application/json"},
                )
            else:
                response = await client.get(url)

            response.raise_for_status()
            return response.text[:3000]

    except httpx.HTTPStatusError as exc:
        return f"Error: {exc.response.status_code} {exc.response.reason_phrase}"
    except httpx.RequestError as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# 2. read_file
# ---------------------------------------------------------------------------


@tool
async def read_file(path: str) -> str:
    """Read a file from the local filesystem and return its text contents (max 5000 chars)."""
    if ".." in path:
        return "Error: path traversal not allowed"
    try:
        async with aiofiles.open(path, mode="r", encoding="utf-8") as f:
            content = await f.read()
        return content[:5000]
    except FileNotFoundError:
        return f"Error: file not found: {path}"
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# 3. write_file
# ---------------------------------------------------------------------------


@tool
async def write_file(path: str, content: str) -> str:
    """Write text content to a file, creating any missing parent directories."""
    if ".." in path:
        return "Error: path traversal not allowed"
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(target, mode="w", encoding="utf-8") as f:
            await f.write(content)
        return f"Written {len(content)} bytes to {path}"
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# 4. run_python
# ---------------------------------------------------------------------------


@tool
async def run_python(code: str) -> str:
    """Execute Python code safely in an isolated Docker container.

    Set AGENTSDK_UNSAFE_PYTHON=1 to fall back to a local subprocess (dev only).
    """
    # Production safe: no network, read-only fs, memory capped
    if os.environ.get("AGENTSDK_UNSAFE_PYTHON"):
        # ── Unsafe local fallback (dev without Docker) ─────────────────────
        # Uses run_in_executor so it works on any event loop (including
        # Windows SelectorEventLoop which rejects create_subprocess_exec).
        def _run_sync() -> str:
            try:
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return result.stdout.decode(errors="replace").strip()
                return f"Error: {result.stderr.decode(errors='replace').strip()}"
            except subprocess.TimeoutExpired:
                return "Error: timeout after 10s"
            except Exception as exc:  # noqa: BLE001
                return f"Error: {exc}"

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_sync)

    # ── Docker sandbox (production) ─────────────────────────────────────────
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        proc = await asyncio.create_subprocess_exec(
            "docker", "run", "--rm",
            "--network", "none",
            "--memory", "128m",
            "--cpus", "0.5",
            "--read-only",
            "--tmpfs", "/tmp:size=64m",
            "-v", f"{tmp_path}:/code/solution.py:ro",
            "python:3.12-slim",
            "python", "/code/solution.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return "Error: timeout after 15s"

        if proc.returncode == 0:
            return stdout.decode(errors="replace").strip()
        return f"Error: {stderr.decode(errors='replace')[:500]}"

    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 5. get_datetime
# ---------------------------------------------------------------------------


@tool
async def get_datetime() -> str:
    """Return the current UTC date and time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 6. ingest_document — RAG ingestion tool
# ---------------------------------------------------------------------------

# Module-level store; set via set_default_store() before using the tool.
_default_store: "VectorMemoryStore | None" = None  # type: ignore[name-defined]  # noqa: F821


def set_default_store(store: "VectorMemoryStore") -> None:  # type: ignore[name-defined]  # noqa: F821
    """Configure the :class:`~agentsdk.memory.VectorMemoryStore` used by
    :func:`ingest_document`.

    Call this once at application start-up before registering
    ``ingest_document`` in an agent.

    Args:
        store: A configured :class:`~agentsdk.memory.VectorMemoryStore` instance.
    """
    global _default_store
    _default_store = store


@tool
async def ingest_document(path: str, session_id: str) -> str:
    """Ingest a text or PDF file into vector memory for semantic retrieval.

    Reads the file at *path*, splits it into overlapping 500-character chunks,
    embeds each chunk, and stores them in the configured vector store under
    *session_id*.

    Supports plain-text files (any extension) and PDF files (``.pdf``).
    For PDF support ``pypdf`` must be installed (``pip install pypdf``).

    Args:
        path: Absolute or relative path to the file to ingest.
        session_id: Session identifier used to namespace the stored chunks.

    Returns:
        A human-readable summary such as ``"Ingested 12 chunks from report.pdf"``,
        or an error string if the store is not configured or the file cannot
        be read.
    """
    if _default_store is None:
        return "Error: no vector store configured. Call set_default_store() first."

    p = Path(path)

    # --- Read content ---
    if p.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore[import]
        except ImportError:
            return (
                "Error: pypdf not installed. "
                "Install it with: pip install pypdf"
            )
        try:
            reader = PdfReader(str(p))
            text = "\n".join(
                page.extract_text() or "" for page in reader.pages
            )
        except Exception as exc:  # noqa: BLE001
            return f"Error reading PDF: {exc}"
    else:
        try:
            async with aiofiles.open(str(p), encoding="utf-8", errors="replace") as f:
                text = await f.read()
        except OSError as exc:
            return f"Error reading file: {exc}"

    if not text.strip():
        return f"Error: no text extracted from {path}"

    # --- Chunk (500 chars, 50-char overlap) ---
    chunk_size, overlap = 500, 50
    step = chunk_size - overlap
    chunks = [
        text[i: i + chunk_size]
        for i in range(0, len(text), step)
        if text[i: i + chunk_size].strip()
    ]

    # --- Store each chunk ---
    for idx, chunk in enumerate(chunks):
        msg = HumanMessage(
            content=chunk,
            metadata={"source": str(p), "chunk": idx},
        )
        await _default_store.add(session_id, msg)

    return f"Ingested {len(chunks)} chunks from {path}"

DEFAULT_TOOLS = ToolRegistry()
DEFAULT_TOOLS.register_many(
    [
        http_request,
        read_file,
        write_file,
        run_python,
        get_datetime,
        ingest_document,
    ]
)
