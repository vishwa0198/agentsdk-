"""agentsdk/mcp/client.py

MCP (Model Context Protocol) client integration.

Connects to an MCP server over stdio or HTTP/SSE and wraps every exposed
tool as a :class:`~agentsdk.tools.base.BaseTool` instance, making them
transparently available to the agent loop and ToolRegistry.

Supported transports
--------------------
* ``"stdio"``  — spawns a local subprocess (e.g. ``npx @modelcontextprotocol/server-filesystem``)
* ``"sse"``    — connects to an HTTP/SSE server (legacy MCP transport)
* ``"http"``   — connects to a Streamable HTTP server (current MCP transport, ≥1.0)

Quick start::

    client = MCPClient(
        name="filesystem",
        transport="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    )
    tools = await client.connect()          # returns list[MCPTool]
    registry = ToolRegistry()
    registry.register_many(tools)
    agent = Agent(config=..., llm=..., registry=registry)
    ...
    await client.disconnect()
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Any

from agentsdk.llm import ToolSchema
from agentsdk.tools.base import BaseTool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy import helpers — mcp is an optional dependency
# ---------------------------------------------------------------------------

def _require_mcp() -> Any:
    """Import the ``mcp`` package or raise a helpful error."""
    try:
        import mcp  # noqa: F401
        return mcp
    except ImportError as exc:
        raise ImportError(
            "The 'mcp' package is required for MCP integration. "
            "Install it with:  pip install 'agentsdk-py[mcp]'  or  pip install mcp"
        ) from exc


# ---------------------------------------------------------------------------
# MCPTool — BaseTool wrapper around a single MCP server tool
# ---------------------------------------------------------------------------

class MCPTool(BaseTool):
    """A :class:`~agentsdk.tools.base.BaseTool` that delegates execution to
    an MCP server tool via a live :class:`mcp.ClientSession`.

    You do not instantiate this directly — :meth:`MCPClient.connect` creates
    one for every tool the server advertises.
    """

    def __init__(self, tool_def: Any, session: Any, server_name: str) -> None:
        self._tool_def = tool_def
        self._session = session
        self._server_name = server_name
        # MCP tool names may contain slashes; replace for safe lookup
        safe_name = tool_def.name.replace("/", "__")
        self._schema = ToolSchema(
            name=safe_name,
            description=tool_def.description or f"MCP tool '{tool_def.name}' from server '{server_name}'",
            parameters=tool_def.inputSchema if tool_def.inputSchema else {"type": "object", "properties": {}},
        )

    # ------------------------------------------------------------------
    # BaseTool interface
    # ------------------------------------------------------------------

    @property
    def schema(self) -> ToolSchema:
        return self._schema

    async def execute(self, **kwargs: Any) -> str:
        """Call the MCP tool and return a plain-string result.

        Raises ``RuntimeError`` if the server reports ``isError=True``.
        """
        logger.debug("MCPTool.execute name=%s args=%s", self._tool_def.name, kwargs)
        result = await self._session.call_tool(self._tool_def.name, kwargs)
        text = _content_to_text(result.content)
        if getattr(result, "isError", False):
            raise RuntimeError(f"MCP tool '{self._tool_def.name}' returned error: {text}")
        return text or ""

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"MCPTool(name={self._schema.name!r}, server={self._server_name!r})"


# ---------------------------------------------------------------------------
# MCPClient — lifecycle manager for one MCP server connection
# ---------------------------------------------------------------------------

class MCPClient:
    """Manages a connection to a single MCP server and exposes its tools.

    Parameters
    ----------
    name:
        Human-readable label for this server (shown in logs and the UI).
    transport:
        One of ``"stdio"``, ``"sse"``, or ``"http"``.
    command:
        *(stdio only)* Executable to run, e.g. ``"npx"``.
    args:
        *(stdio only)* Arguments passed to *command*.
    env:
        *(stdio only)* Optional extra environment variables for the subprocess.
    url:
        *(sse / http only)* Full URL of the MCP server endpoint.

    Examples
    --------
    stdio::

        client = MCPClient("fs", transport="stdio",
                           command="npx",
                           args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"])

    HTTP/SSE::

        client = MCPClient("brave", transport="sse",
                           url="http://localhost:8080/sse")

    Streamable HTTP (≥MCP 1.0)::

        client = MCPClient("custom", transport="http",
                           url="http://localhost:9000/mcp")
    """

    def __init__(
        self,
        name: str,
        transport: str,
        *,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
    ) -> None:
        transport = transport.lower()
        if transport not in ("stdio", "sse", "http"):
            raise ValueError(f"transport must be 'stdio', 'sse', or 'http'; got {transport!r}")
        if transport == "stdio" and not command:
            raise ValueError("transport='stdio' requires 'command'")
        if transport in ("sse", "http") and not url:
            raise ValueError(f"transport={transport!r} requires 'url'")

        self.name = name
        self.transport = transport
        self._command = command
        self._args: list[str] = args or []
        self._env: dict[str, str] | None = env
        self._url = url

        self._exit_stack = AsyncExitStack()
        self._session: Any | None = None
        self._tools: list[MCPTool] = []
        self._connected = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> list[MCPTool]:
        """Connect to the MCP server, initialise the session, and return
        the list of :class:`MCPTool` instances (one per advertised tool).

        Call :meth:`disconnect` when finished to release resources.
        """
        if self._connected:
            logger.warning("MCPClient '%s' is already connected", self.name)
            return self._tools

        _require_mcp()

        from mcp import ClientSession, StdioServerParameters  # type: ignore[import]

        logger.info("MCPClient '%s': connecting via %s", self.name, self.transport)

        if self.transport == "stdio":
            from mcp.client.stdio import stdio_client  # type: ignore[import]
            read, write = await self._exit_stack.enter_async_context(
                stdio_client(StdioServerParameters(
                    command=self._command,
                    args=self._args,
                    env=self._env,
                ))
            )
        elif self.transport == "sse":
            from mcp.client.sse import sse_client  # type: ignore[import]
            read, write = await self._exit_stack.enter_async_context(
                sse_client(self._url)
            )
        else:  # http — streamable HTTP (MCP ≥1.0)
            from mcp.client.streamable_http import streamablehttp_client  # type: ignore[import]
            read, write, _ = await self._exit_stack.enter_async_context(
                streamablehttp_client(self._url)
            )

        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session

        tool_list = await session.list_tools()
        self._tools = [
            MCPTool(t, session, self.name)
            for t in tool_list.tools
        ]
        self._connected = True
        logger.info(
            "MCPClient '%s': connected — %d tool(s): %s",
            self.name,
            len(self._tools),
            [t.schema.name for t in self._tools],
        )
        return self._tools

    async def disconnect(self) -> None:
        """Cleanly shut down the session and release all resources."""
        if not self._connected:
            return
        await self._exit_stack.aclose()
        self._session = None
        self._tools = []
        self._connected = False
        logger.info("MCPClient '%s': disconnected", self.name)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def tools(self) -> list[MCPTool]:
        """Currently connected tools (empty before :meth:`connect`)."""
        return list(self._tools)

    @property
    def connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Async context manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "MCPClient":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.disconnect()

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"MCPClient(name={self.name!r}, transport={self.transport!r}, status={status})"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _content_to_text(content_list: list[Any]) -> str:
    """Flatten a list of MCP content objects to a single string."""
    parts: list[str] = []
    for item in content_list or []:
        if hasattr(item, "text"):
            parts.append(item.text)
        elif hasattr(item, "data"):
            # ImageContent — return a placeholder; agents can describe it
            parts.append("[image data]")
        elif isinstance(item, str):
            parts.append(item)
        else:
            parts.append(str(item))
    return "\n".join(parts)
