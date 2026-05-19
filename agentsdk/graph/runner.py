"""agentsdk/graph/runner.py

GraphRunner — executes an AgentGraph level-by-level with parallel nodes.
"""

from __future__ import annotations

import asyncio
from typing import Any

from agentsdk.exceptions import GraphExecutionError
from agentsdk.graph.graph import AgentGraph
from agentsdk.graph.node import NodeInput, NodeOutput


class GraphRunner:
    """Executes an AgentGraph respecting its topological order.

    Nodes on the same level run concurrently via ``asyncio.gather``.
    The first failing node immediately aborts the run (fail-fast).

    Args:
        graph: The AgentGraph to execute.

    Example::

        runner = GraphRunner(graph)
        output = await runner.run({"input": "Hello"})
    """

    def __init__(self, graph: AgentGraph) -> None:
        self._graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, initial_input: dict[str, Any]) -> dict[str, Any]:
        """Execute the graph and return the exit node's output data.

        Parameters
        ----------
        initial_input:
            Seed data given to the entry node.

        Returns
        -------
        dict[str, Any]
            The ``NodeOutput.data`` dict produced by the exit node.

        Raises
        ------
        ValueError
            If the graph has no entry or exit node set.
        GraphExecutionError
            On the first node failure (fail-fast semantics).
        """
        graph = self._graph

        if graph._entry is None:
            raise ValueError("Graph has no entry node. Call graph.set_entry() first.")
        if graph._exit is None:
            raise ValueError("Graph has no exit node. Call graph.set_exit() first.")

        levels = graph._topological_sort()
        results: dict[str, NodeOutput] = {}

        for level in levels:
            # Build inputs for every node in this level before launching any.
            tasks = [
                graph._nodes[node_id].run(
                    self._build_node_input(node_id, results, initial_input)
                )
                for node_id in level
            ]

            # Run the whole level in parallel.
            outputs: list[NodeOutput] = await asyncio.gather(*tasks)

            for node_id, output in zip(level, outputs):
                if not output.success:
                    raise GraphExecutionError(
                        node_id=node_id,
                        reason=output.error or "unknown error",
                    )
                results[node_id] = output

        return results[graph._exit].data

    async def run_safe(
        self, initial_input: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Like :meth:`run` but never raises.

        Returns
        -------
        (result, None)
            On success — ``result`` is the exit node's output data.
        (None, error_message)
            On failure — ``error_message`` is the stringified exception.
        """
        try:
            return await self.run(initial_input), None
        except GraphExecutionError as exc:
            return None, str(exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_node_input(
        self,
        node_id: str,
        results: dict[str, NodeOutput],
        initial_input: dict[str, Any],
    ) -> NodeInput:
        """Construct the :class:`NodeInput` for *node_id*.

        - Entry node → always receives ``initial_input`` unchanged.
        - All other nodes → parent outputs are collected, keys are remapped
          through ``Edge.data_map`` (if set), then merged into one dict.
        """
        if node_id == self._graph._entry:
            return NodeInput(node_id=node_id, data=dict(initial_input))

        parent_edges = [e for e in self._graph._edges if e.to_node == node_id]
        merged: dict[str, Any] = {}

        for edge in parent_edges:
            parent_data = results[edge.from_node].data
            if edge.data_map:
                # Selective key rename: {upstream_key: downstream_key}
                for from_key, to_key in edge.data_map.items():
                    if from_key in parent_data:
                        merged[to_key] = parent_data[from_key]
            else:
                # No mapping → pass all upstream keys through unchanged.
                merged.update(parent_data)

        return NodeInput(node_id=node_id, data=merged)
