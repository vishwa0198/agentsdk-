"""tests/test_mcp.py

Unit tests for the MCP integration layer.

All tests use unittest.mock to simulate an MCP server — no real subprocess
or network connection is required.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentsdk.mcp.client import MCPClient, MCPTool, _content_to_text
from agentsdk.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Helpers — build fake MCP objects
# ---------------------------------------------------------------------------

def _make_tool_def(name: str, description: str = "A test tool", schema: dict | None = None):
    """Create a minimal fake MCP Tool definition."""
    return SimpleNamespace(
        name=name,
        description=description,
        inputSchema=schema or {"type": "object", "properties": {"arg": {"type": "string"}}},
    )


def _make_text_content(text: str):
    return SimpleNamespace(text=text)


def _make_call_result(text: str, is_error: bool = False):
    return SimpleNamespace(
        content=[_make_text_content(text)],
        isError=is_error,
    )


def _make_list_tools_result(tools):
    return SimpleNamespace(tools=tools)


# ---------------------------------------------------------------------------
# Fixture — mocked MCPClient that never touches the network
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session():
    """An AsyncMock that behaves like mcp.ClientSession."""
    session = AsyncMock()
    session.initialize = AsyncMock(return_value=None)
    session.list_tools = AsyncMock(return_value=_make_list_tools_result([
        _make_tool_def("read_file", "Read a file"),
        _make_tool_def("write_file", "Write a file"),
        _make_tool_def("list_dir", "List directory"),
    ]))
    session.call_tool = AsyncMock(return_value=_make_call_result("file contents"))
    return session


# ---------------------------------------------------------------------------
# _content_to_text
# ---------------------------------------------------------------------------

class TestContentToText:
    def test_single_text_content(self):
        assert _content_to_text([SimpleNamespace(text="hello")]) == "hello"

    def test_multiple_text_contents(self):
        items = [SimpleNamespace(text="line1"), SimpleNamespace(text="line2")]
        assert _content_to_text(items) == "line1\nline2"

    def test_image_content(self):
        item = SimpleNamespace(data=b"\x89PNG")  # no .text attribute
        result = _content_to_text([item])
        assert result == "[image data]"

    def test_empty_list(self):
        assert _content_to_text([]) == ""

    def test_string_item(self):
        assert _content_to_text(["raw string"]) == "raw string"


# ---------------------------------------------------------------------------
# MCPTool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMCPTool:
    async def test_schema_populated(self):
        session = AsyncMock()
        tool_def = _make_tool_def("my_tool", "Does stuff")
        tool = MCPTool(tool_def, session, server_name="test_server")

        assert tool.schema.name == "my_tool"
        assert tool.schema.description == "Does stuff"
        assert "properties" in tool.schema.parameters

    async def test_execute_returns_text(self):
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=_make_call_result("hello world"))
        tool = MCPTool(_make_tool_def("greet"), session, "srv")

        result = await tool.execute(name="Alice")
        assert result == "hello world"
        session.call_tool.assert_called_once_with("greet", {"name": "Alice"})

    async def test_execute_raises_on_error_result(self):
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=_make_call_result("permission denied", is_error=True))
        tool = MCPTool(_make_tool_def("read"), session, "srv")

        with pytest.raises(RuntimeError, match="permission denied"):
            await tool.execute(path="/etc/shadow")

    async def test_tool_name_slash_replaced(self):
        """Tool names with slashes (e.g. 'tools/read') are normalised to double-underscore."""
        tool_def = _make_tool_def("tools/read")
        tool = MCPTool(tool_def, AsyncMock(), "srv")
        assert tool.schema.name == "tools__read"

    async def test_execute_empty_result(self):
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=SimpleNamespace(content=[], isError=False))
        tool = MCPTool(_make_tool_def("noop"), session, "srv")
        result = await tool.execute()
        assert result == ""


# ---------------------------------------------------------------------------
# MCPClient — validation
# ---------------------------------------------------------------------------

class TestMCPClientValidation:
    def test_invalid_transport_raises(self):
        with pytest.raises(ValueError, match="transport must be"):
            MCPClient("srv", transport="grpc")

    def test_stdio_without_command_raises(self):
        with pytest.raises(ValueError, match="requires 'command'"):
            MCPClient("srv", transport="stdio")

    def test_sse_without_url_raises(self):
        with pytest.raises(ValueError, match="requires 'url'"):
            MCPClient("srv", transport="sse")

    def test_http_without_url_raises(self):
        with pytest.raises(ValueError, match="requires 'url'"):
            MCPClient("srv", transport="http")

    def test_valid_stdio_config(self):
        c = MCPClient("fs", transport="stdio", command="npx", args=["-y", "some-server"])
        assert c.name == "fs"
        assert c.transport == "stdio"
        assert not c.connected

    def test_valid_sse_config(self):
        c = MCPClient("search", transport="sse", url="http://localhost:8080/sse")
        assert c.transport == "sse"


# ---------------------------------------------------------------------------
# MCPClient — connect / disconnect (mocked transports)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMCPClientConnect:
    async def _patched_client(self, transport: str, session: AsyncMock) -> MCPClient:
        """Return an MCPClient with all transport calls mocked."""
        rw = (AsyncMock(), AsyncMock())
        rw_http = (AsyncMock(), AsyncMock(), None)

        if transport == "stdio":
            client = MCPClient("srv", transport="stdio", command="npx", args=[])
            patch_path = "agentsdk.mcp.client._get_stdio_client"
        elif transport == "sse":
            client = MCPClient("srv", transport="sse", url="http://localhost/sse")
            patch_path = "agentsdk.mcp.client._get_sse_client"
        else:
            client = MCPClient("srv", transport="http", url="http://localhost/mcp")
            patch_path = "agentsdk.mcp.client._get_streamablehttp_client"

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=rw if transport != "http" else rw_http)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        transport_client = MagicMock(return_value=mock_ctx)

        session_ctx = MagicMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("agentsdk.mcp.client._require_mcp", return_value=object()),
            patch(patch_path, return_value=transport_client),
            patch("agentsdk.mcp.client._get_client_session", return_value=MagicMock(return_value=session_ctx)),
            patch("agentsdk.mcp.client._get_stdio_server_parameters", return_value=MagicMock()),
        ):
            tools = await client.connect()

        return client, tools

    async def test_connect_returns_tools(self, mock_session):
        client, tools = await self._patched_client("stdio", mock_session)
        assert client.connected
        assert len(tools) == 3
        assert tools[0].schema.name == "read_file"

    async def test_tools_property(self, mock_session):
        client, _ = await self._patched_client("stdio", mock_session)
        assert len(client.tools) == 3

    async def test_double_connect_is_noop(self, mock_session):
        """Calling connect() on an already-connected client is a no-op."""
        client, _ = await self._patched_client("stdio", mock_session)
        original_tools = client.tools
        tools2 = await client.connect()  # already connected → same list returned
        assert tools2 == original_tools

    async def test_disconnect_clears_state(self, mock_session):
        client, _ = await self._patched_client("stdio", mock_session)
        assert client.connected
        await client.disconnect()
        assert not client.connected
        assert client.tools == []

    async def test_disconnect_when_not_connected_is_safe(self):
        client = MCPClient("srv", transport="stdio", command="npx")
        await client.disconnect()  # must not raise


# ---------------------------------------------------------------------------
# ToolRegistry integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mcp_tools_register_in_registry(mock_session):
    """MCPTool instances can be registered and dispatched from a ToolRegistry."""
    tools = [
        MCPTool(_make_tool_def("search"), mock_session, "brave"),
        MCPTool(_make_tool_def("index"), mock_session, "brave"),
    ]
    registry = ToolRegistry()
    registry.register_many(tools)

    assert len(registry.all()) == 2
    assert "search" in registry
    tool = registry.get("search")
    assert tool is not None

    mock_session.call_tool = AsyncMock(return_value=_make_call_result("result"))
    result = await tool.execute(query="python")
    assert result == "result"


# ---------------------------------------------------------------------------
# MCPManager unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMCPManager:
    async def test_add_and_list_server(self):
        from webui.backend.mcp_manager import MCPManager  # type: ignore[import]
        mgr = MCPManager()
        sid = await mgr.add_server("alice", {
            "name": "fs", "transport": "stdio", "command": "npx", "args": [],
        })
        servers = mgr.list_servers("alice")
        assert len(servers) == 1
        assert servers[0]["id"] == sid
        assert servers[0]["connected"] is False

    async def test_remove_server(self):
        from webui.backend.mcp_manager import MCPManager  # type: ignore[import]
        mgr = MCPManager()
        sid = await mgr.add_server("alice", {
            "name": "fs", "transport": "stdio", "command": "npx",
        })
        await mgr.remove_server("alice", sid)
        assert mgr.list_servers("alice") == []

    async def test_remove_nonexistent_raises(self):
        from webui.backend.mcp_manager import MCPManager  # type: ignore[import]
        mgr = MCPManager()
        with pytest.raises(KeyError):
            await mgr.remove_server("alice", "bad-id")

    async def test_get_tools_empty_when_no_servers(self):
        from webui.backend.mcp_manager import MCPManager  # type: ignore[import]
        mgr = MCPManager()
        assert mgr.get_tools("alice") == []
