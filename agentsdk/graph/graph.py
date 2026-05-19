"""agentsdk/graph/graph.py

AgentGraph — DAG container with Kahn's-algorithm topological sort.
"""

from __future__ import annotations

from typing import Any

from agentsdk.graph.node import AgentNode, Edge


class AgentGraph:
    """A directed acyclic graph of AgentNode instances.

    Nodes run in topological order; nodes on the same level execute in
    parallel (handled by GraphRunner).

    Example::

        graph = AgentGraph()
        graph.add_node(AgentNode(node_id="a", agent=agent_a))
        graph.add_node(AgentNode(node_id="b", agent=agent_b))
        graph.add_edge(Edge(from_node="a", to_node="b"))
        graph.set_entry("a")
        graph.set_exit("b")
    """

    def __init__(self) -> None:
        self._nodes: dict[str, AgentNode] = {}
        self._edges: list[Edge] = []
        self._entry: str | None = None
        self._exit: str | None = None

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def add_node(self, node: AgentNode) -> None:
        """Register *node* in the graph.

        Raises
        ------
        ValueError
            If a node with the same ``node_id`` is already registered.
        """
        if node.node_id in self._nodes:
            raise ValueError(f"Node '{node.node_id}' is already in the graph.")
        self._nodes[node.node_id] = node

    def add_edge(self, edge: Edge) -> None:
        """Add a directed edge from ``edge.from_node`` to ``edge.to_node``.

        Raises
        ------
        ValueError
            If either endpoint node has not been added to the graph.
        """
        if edge.from_node not in self._nodes:
            raise ValueError(
                f"Edge source '{edge.from_node}' is not a registered node."
            )
        if edge.to_node not in self._nodes:
            raise ValueError(
                f"Edge target '{edge.to_node}' is not a registered node."
            )
        self._edges.append(edge)

    def set_entry(self, node_id: str) -> None:
        """Designate *node_id* as the graph's entry point."""
        if node_id not in self._nodes:
            raise ValueError(f"Entry node '{node_id}' is not registered.")
        self._entry = node_id

    def set_exit(self, node_id: str) -> None:
        """Designate *node_id* as the graph's exit / output node."""
        if node_id not in self._nodes:
            raise ValueError(f"Exit node '{node_id}' is not registered.")
        self._exit = node_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_dependencies(self, node_id: str) -> list[str]:
        """Return the ``node_id`` of every node that has an edge *into* *node_id*."""
        return [e.from_node for e in self._edges if e.to_node == node_id]

    def _topological_sort(self) -> list[list[str]]:
        """Return execution levels using Kahn's algorithm.

        Each level is a list of node IDs that can run in parallel because
        all their dependencies have already completed.

        Raises
        ------
        ValueError
            If the graph contains a cycle.
        """
        # Build in-degree count and adjacency list.
        in_degree: dict[str, int] = {nid: 0 for nid in self._nodes}
        adjacency: dict[str, list[str]] = {nid: [] for nid in self._nodes}

        for edge in self._edges:
            in_degree[edge.to_node] += 1
            adjacency[edge.from_node].append(edge.to_node)

        # Level 0: all nodes with no incoming edges.
        current_level = [nid for nid, deg in in_degree.items() if deg == 0]
        levels: list[list[str]] = []
        visited = 0

        while current_level:
            levels.append(current_level)
            visited += len(current_level)
            next_level: list[str] = []
            for nid in current_level:
                for successor in adjacency[nid]:
                    in_degree[successor] -= 1
                    if in_degree[successor] == 0:
                        next_level.append(successor)
            current_level = next_level

        if visited != len(self._nodes):
            raise ValueError(
                "Cycle detected in the agent graph — DAG execution is not possible."
            )

        return levels

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"AgentGraph("
            f"nodes={list(self._nodes.keys())}, "
            f"entry={self._entry!r}, "
            f"exit={self._exit!r})"
        )
