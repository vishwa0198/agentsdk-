"""agentsdk/graph/node.py

Data types and the AgentNode wrapper for a single graph vertex.

Import chain (no circular dependencies):
    graph/node.py → agentsdk.agent → agentsdk.llm → agentsdk.messages
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

from agentsdk.agent import Agent


# ---------------------------------------------------------------------------
# NodeInput / NodeOutput — typed data flowing between nodes
# ---------------------------------------------------------------------------


class NodeInput(BaseModel):
    """Arbitrary payload entering a node."""

    model_config = ConfigDict(frozen=True)

    node_id: str
    data: dict[str, Any]


class NodeOutput(BaseModel):
    """Result produced by a node after execution."""

    model_config = ConfigDict(frozen=True)

    node_id: str
    data: dict[str, Any]
    success: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# Edge — a directed connection between two nodes
# ---------------------------------------------------------------------------


class Edge(BaseModel):
    """A directed edge from one node to another.

    data_map controls how the upstream node's output dict is transformed
    into the downstream node's input dict:

    - Empty dict (default): pass the full data dict through unchanged.
    - Non-empty: each ``{from_key: to_key}`` pair renames a key.
      Keys absent from the upstream output are silently skipped.
    """

    model_config = ConfigDict(frozen=True)

    from_node: str
    to_node: str
    data_map: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# AgentNode — a single vertex in the graph
# ---------------------------------------------------------------------------


@dataclass
class AgentNode:
    """Wraps an :class:`~agentsdk.agent.Agent` as a graph node.

    Parameters
    ----------
    node_id:
        Unique identifier within the graph.
    agent:
        The agent that handles this node's workload.
    input_key:
        Key in ``NodeInput.data`` to extract as the agent's ``user_input``.
    output_key:
        Key under which the agent's response string is stored in
        ``NodeOutput.data``.
    """

    node_id: str
    agent: Agent
    input_key: str = "input"
    output_key: str = "output"

    async def run(self, node_input: NodeInput) -> NodeOutput:
        """Execute the wrapped agent and return a :class:`NodeOutput`.

        Handles both hard exceptions and agent-level errors (``stopped_by="error"``),
        surfacing either as a failed ``NodeOutput`` so the graph runner can abort.
        """
        user_input = str(node_input.data.get(self.input_key, ""))
        try:
            result = await self.agent.run(user_input)
            if result.stopped_by == "error":
                return NodeOutput(
                    node_id=self.node_id,
                    data={},
                    success=False,
                    error=result.output,
                )
            return NodeOutput(
                node_id=self.node_id,
                data={self.output_key: result.output},
                success=True,
            )
        except Exception as exc:  # noqa: BLE001
            return NodeOutput(
                node_id=self.node_id,
                data={},
                success=False,
                error=str(exc),
            )
