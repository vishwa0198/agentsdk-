"""agentsdk/mcp

MCP (Model Context Protocol) integration for agentsdk.

Exports
-------
MCPClient
    Connects to an MCP server and exposes its tools as BaseTool instances.
MCPTool
    A BaseTool that delegates execution to an MCP server tool.

Usage::

    from agentsdk.mcp import MCPClient

    async with MCPClient("filesystem", transport="stdio",
                         command="npx",
                         args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]) as client:
        agent = Agent(config=..., llm=..., tools=client.tools)
        result = await agent.run("List the files in /tmp")

Requires the optional ``mcp`` package::

    pip install 'agentsdk-py[mcp]'
"""

from agentsdk.mcp.client import MCPClient, MCPTool

__all__ = ["MCPClient", "MCPTool"]
