"""agentsdk — A lightweight Python SDK for building AI agents."""

from agentsdk.agent import Agent, AgentConfig, AgentResult
from agentsdk.messages import (
    MessageHistory,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolResultMessage,
)
from agentsdk.llm import GroqProvider, LLMResponse
from agentsdk.tools.base import tool, BaseTool
from agentsdk.tools.registry import ToolRegistry
from agentsdk.tools.builtin import DEFAULT_TOOLS
from agentsdk.graph.node import AgentNode, Edge
from agentsdk.graph.graph import AgentGraph
from agentsdk.graph.runner import GraphRunner
from agentsdk.graph.bus import MessageBus, BusAwareAgent, BusRunner
from agentsdk.persistence.file_store import FileCheckpointStore
from agentsdk.persistence.session import SessionManager

__version__ = "0.1.0"

__all__ = [
    # Core agent
    "Agent", "AgentConfig", "AgentResult",
    # Messages
    "MessageHistory", "HumanMessage", "AIMessage", "SystemMessage", "ToolResultMessage",
    # LLM
    "GroqProvider", "LLMResponse",
    # Tools
    "tool", "BaseTool", "ToolRegistry", "DEFAULT_TOOLS",
    # Graph
    "AgentNode", "Edge", "AgentGraph", "GraphRunner",
    # Bus
    "MessageBus", "BusAwareAgent", "BusRunner",
    # Persistence
    "FileCheckpointStore", "SessionManager",
    # Meta
    "__version__",
]
