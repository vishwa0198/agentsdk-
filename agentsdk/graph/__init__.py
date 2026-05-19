"""agentsdk/graph

Multi-agent orchestration via a directed acyclic graph (DAG) and an
async inter-agent message bus.

Quick start — DAG pipeline::

    from agentsdk.graph import AgentGraph, AgentNode, Edge, GraphRunner

Quick start — message bus::

    from agentsdk.graph import MessageBus, BusAwareAgent, BusRunner
"""

from agentsdk.graph.bus import BusAwareAgent, BusMessage, BusRunner, MessageBus
from agentsdk.graph.graph import AgentGraph
from agentsdk.graph.node import AgentNode, Edge, NodeInput, NodeOutput
from agentsdk.graph.runner import GraphRunner

__all__ = [
    "AgentGraph",
    "AgentNode",
    "BusAwareAgent",
    "BusMessage",
    "BusRunner",
    "Edge",
    "GraphRunner",
    "MessageBus",
    "NodeInput",
    "NodeOutput",
]
