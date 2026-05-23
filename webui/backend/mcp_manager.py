"""webui/backend/mcp_manager.py

Manages MCP server connections for the web UI.

Each *user* has their own list of configured MCP servers.  Servers can be
connected (live session) or disconnected (config stored, session closed).
When connected, their tools are injected into the matching Agent session.

Thread-safety: all mutations happen inside the same async event loop —
FastAPI/uvicorn with a single worker — so plain dicts are fine.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from agentsdk.mcp.client import MCPClient, MCPTool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class MCPServerConfig:
    """Persisted config for one MCP server (survives disconnect)."""
    id: str
    name: str
    transport: str          # "stdio" | "sse" | "http"
    # stdio fields
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    # sse / http fields
    url: str | None = None


@dataclass
class MCPServerState:
    """Runtime state for one MCP server connection."""
    config: MCPServerConfig
    client: MCPClient | None = None
    tools: list[MCPTool] = field(default_factory=list)
    connected: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# MCPManager
# ---------------------------------------------------------------------------

class MCPManager:
    """Per-user registry of MCP server configs and live connections.

    Usage
    -----
    ::

        mcp_manager = MCPManager()

        # Add a server config (does not connect yet)
        server_id = await mcp_manager.add_server(username, {
            "name": "filesystem",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        })

        # Connect to the server
        tools = await mcp_manager.connect(username, server_id)

        # Get all tools for a user (across all connected servers)
        tools = mcp_manager.get_tools(username)
    """

    def __init__(self) -> None:
        # user → {server_id → MCPServerState}
        self._states: dict[str, dict[str, MCPServerState]] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _user_states(self, username: str) -> dict[str, MCPServerState]:
        if username not in self._states:
            self._states[username] = {}
        return self._states[username]

    def _get_state(self, username: str, server_id: str) -> MCPServerState:
        states = self._user_states(username)
        if server_id not in states:
            raise KeyError(f"MCP server '{server_id}' not found for user '{username}'")
        return states[server_id]

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def add_server(self, username: str, cfg: dict) -> str:
        """Register a new MCP server config and return its generated ID."""
        server_id = str(uuid.uuid4())[:8]
        config = MCPServerConfig(
            id=server_id,
            name=cfg["name"],
            transport=cfg["transport"],
            command=cfg.get("command"),
            args=cfg.get("args") or [],
            env=cfg.get("env"),
            url=cfg.get("url"),
        )
        self._user_states(username)[server_id] = MCPServerState(config=config)
        logger.info("MCPManager: user=%s added server id=%s name=%s", username, server_id, config.name)
        return server_id

    def list_servers(self, username: str) -> list[dict]:
        """Return a JSON-serialisable summary of all servers for a user."""
        return [
            {
                "id": state.config.id,
                "name": state.config.name,
                "transport": state.config.transport,
                "command": state.config.command,
                "args": state.config.args,
                "url": state.config.url,
                "connected": state.connected,
                "tool_count": len(state.tools),
                "tool_names": [t.schema.name for t in state.tools],
                "error": state.error,
            }
            for state in self._user_states(username).values()
        ]

    async def remove_server(self, username: str, server_id: str) -> None:
        """Disconnect (if connected) and remove the server config."""
        state = self._get_state(username, server_id)
        if state.connected:
            await self._do_disconnect(state)
        del self._user_states(username)[server_id]
        logger.info("MCPManager: user=%s removed server id=%s", username, server_id)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, username: str, server_id: str) -> list[dict]:
        """Connect to the server and return the list of tool summaries."""
        state = self._get_state(username, server_id)
        if state.connected:
            return [{"name": t.schema.name, "description": t.schema.description}
                    for t in state.tools]
        cfg = state.config
        client = MCPClient(
            name=cfg.name,
            transport=cfg.transport,
            command=cfg.command,
            args=cfg.args,
            env=cfg.env,
            url=cfg.url,
        )
        try:
            tools = await client.connect()
            state.client = client
            state.tools = tools
            state.connected = True
            state.error = None
            logger.info(
                "MCPManager: user=%s connected server=%s tools=%d",
                username, server_id, len(tools),
            )
        except Exception as exc:
            state.error = str(exc)
            logger.error("MCPManager: connect failed user=%s server=%s: %s", username, server_id, exc)
            raise

        return [
            {"name": t.schema.name, "description": t.schema.description}
            for t in state.tools
        ]

    async def disconnect(self, username: str, server_id: str) -> None:
        """Disconnect from the server, releasing the subprocess/connection."""
        state = self._get_state(username, server_id)
        if not state.connected:
            return
        await self._do_disconnect(state)
        logger.info("MCPManager: user=%s disconnected server=%s", username, server_id)

    async def _do_disconnect(self, state: MCPServerState) -> None:
        if state.client:
            await state.client.disconnect()
        state.client = None
        state.tools = []
        state.connected = False
        state.error = None

    async def disconnect_all(self, username: str) -> None:
        """Disconnect all servers for a user (called on logout / cleanup)."""
        for state in list(self._user_states(username).values()):
            if state.connected:
                await self._do_disconnect(state)

    # ------------------------------------------------------------------
    # Tool access (used by AgentManager)
    # ------------------------------------------------------------------

    def get_tools(self, username: str) -> list[MCPTool]:
        """Return all live MCPTool instances for a user across all connected servers."""
        tools: list[MCPTool] = []
        for state in self._user_states(username).values():
            if state.connected:
                tools.extend(state.tools)
        return tools
