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
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
import httpx

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
    """Execute a Python code snippet in a subprocess and return its stdout output.

    Hard timeout of 10 seconds. Returns stderr on non-zero exit.
    """
    # WARNING: unsafe, dev only — no sandboxing. Full sandboxing is Phase 2 Step 3.
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return "Error: timeout after 10s"

        if proc.returncode == 0:
            return stdout.decode(errors="replace").strip()
        return f"Error: {stderr.decode(errors='replace').strip()}"

    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# 5. get_datetime
# ---------------------------------------------------------------------------


@tool
async def get_datetime() -> str:
    """Return the current UTC date and time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# DEFAULT_TOOLS — pre-built registry ready to pass to Agent
# ---------------------------------------------------------------------------

DEFAULT_TOOLS = ToolRegistry()
DEFAULT_TOOLS.register_many(
    [
        http_request,
        read_file,
        write_file,
        run_python,
        get_datetime,
    ]
)
