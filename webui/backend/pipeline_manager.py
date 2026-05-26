"""webui/backend/pipeline_manager.py

Manages pipeline configs — persistence and execution.

Pipelines are saved as JSON under .agentsdk/pipelines/{id}.json.
Execution builds a real AgentGraph + GraphRunner from the config and runs
it, returning per-node results so the UI can colour each node.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from agentsdk import Agent, AgentConfig, OllamaProvider
from agentsdk.graph.graph import AgentGraph
from agentsdk.graph.node import AgentNode, Edge, NodeInput, NodeOutput
from agentsdk.tools.builtin import DEFAULT_TOOLS

from models import (
    PipelineConfig,
    PipelineEdgeConfig,
    PipelineNodeConfig,
    PipelineNodeResult,
    PipelineRunResult,
)

# ---------------------------------------------------------------------------
# Storage directory
# ---------------------------------------------------------------------------

_PIPELINES_DIR = Path(".agentsdk") / "pipelines"


def _pipeline_path(pipeline_id: str) -> Path:
    return _PIPELINES_DIR / f"{pipeline_id}.json"


# ---------------------------------------------------------------------------
# PipelineManager
# ---------------------------------------------------------------------------

class PipelineManager:
    """Save, load, list, and execute pipelines.

    All pipeline configs are stored as JSON files; execution spins up
    real ``Agent`` instances per node using the stored node configs.
    """

    def __init__(self) -> None:
        load_dotenv(find_dotenv(usecwd=True), override=True)
        _PIPELINES_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, config: PipelineConfig) -> None:
        """Write *config* to disk, overwriting any existing pipeline with the same id."""
        _PIPELINES_DIR.mkdir(parents=True, exist_ok=True)
        _pipeline_path(config.id).write_text(
            config.model_dump_json(indent=2), encoding="utf-8"
        )

    def load(self, pipeline_id: str) -> PipelineConfig | None:
        """Return the pipeline config for *pipeline_id*, or ``None`` if not found."""
        path = _pipeline_path(pipeline_id)
        if not path.exists():
            return None
        try:
            return PipelineConfig.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def list_all(self) -> list[PipelineConfig]:
        """Return all saved pipeline configs, sorted by name."""
        configs: list[PipelineConfig] = []
        for path in _PIPELINES_DIR.glob("*.json"):
            try:
                configs.append(
                    PipelineConfig.model_validate_json(path.read_text(encoding="utf-8"))
                )
            except Exception:
                pass
        return sorted(configs, key=lambda c: c.name.lower())

    def delete(self, pipeline_id: str) -> bool:
        """Delete the pipeline file. Returns True if it existed."""
        path = _pipeline_path(pipeline_id)
        if path.exists():
            path.unlink()
            return True
        return False

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def run(
        self,
        config: PipelineConfig,
        initial_input: str,
    ) -> PipelineRunResult:
        """Execute *config* and return per-node results.

        Each node gets its own ``Agent`` instance using the node's model /
        max_iterations settings.  Nodes on the same topological level run
        concurrently (same behaviour as GraphRunner).
        """
        if not config.nodes:
            return PipelineRunResult(success=False, error="Pipeline has no nodes.")
        if not config.entry_node:
            return PipelineRunResult(success=False, error="No entry node set.")
        if not config.exit_node:
            return PipelineRunResult(success=False, error="No exit node set.")

        api_key = ""  # Ollama is local — no API key required
        node_map: dict[str, PipelineNodeConfig] = {n.id: n for n in config.nodes}

        # Auto-wire sequential edges when none are drawn.
        # Order: entry → (middle nodes in config order) → exit
        # Maps each node's output_key → next node's input_key so data flows correctly.
        if not config.edges and len(config.nodes) >= 2:
            middle = [n.id for n in config.nodes
                      if n.id != config.entry_node and n.id != config.exit_node]
            ordered_ids = [config.entry_node] + middle + [config.exit_node]
            auto_edges: list[PipelineEdgeConfig] = []
            for i in range(len(ordered_ids) - 1):
                src = node_map[ordered_ids[i]]
                dst = node_map[ordered_ids[i + 1]]
                auto_edges.append(PipelineEdgeConfig(
                    from_node=src.id,
                    to_node=dst.id,
                    data_map={src.output_key: dst.input_key},
                ))
            config = PipelineConfig(**{**config.model_dump(), "edges": [e.model_dump() for e in auto_edges]})
        node_results: dict[str, PipelineNodeResult] = {}

        # DEFAULT_TOOLS is a ToolRegistry — pass it directly to each Agent.

        # Build the AgentGraph.
        graph = AgentGraph()
        for node_cfg in config.nodes:
            model = node_cfg.model or os.environ.get("OLLAMA_MODEL", "llama3:8b")
            llm = OllamaProvider(model=model)
            agent_cfg = AgentConfig(
                name=node_cfg.name,
                system_prompt=node_cfg.system_prompt,
                max_iterations=node_cfg.max_iterations,
                max_tokens=1024,
            )
            agent = Agent(config=agent_cfg, llm=llm, registry=DEFAULT_TOOLS)
            graph.add_node(AgentNode(
                node_id=node_cfg.id,
                agent=agent,
                input_key=node_cfg.input_key,
                output_key=node_cfg.output_key,
            ))

        for edge_cfg in config.edges:
            graph.add_edge(Edge(
                from_node=edge_cfg.from_node,
                to_node=edge_cfg.to_node,
                data_map=edge_cfg.data_map,
            ))

        graph.set_entry(config.entry_node)
        graph.set_exit(config.exit_node)

        # Run level-by-level, collecting all node results.
        try:
            levels = graph._topological_sort()
        except ValueError as exc:
            return PipelineRunResult(success=False, error=str(exc))

        completed: dict[str, NodeOutput] = {}
        final_output: str | None = None

        for level in levels:
            tasks = [
                graph._nodes[nid].run(
                    _build_input(nid, completed, {"input": initial_input}, graph)
                )
                for nid in level
            ]
            outputs: list[NodeOutput] = await asyncio.gather(*tasks)

            for nid, out in zip(level, outputs):
                completed[nid] = out
                node_cfg = node_map[nid]
                node_results[nid] = PipelineNodeResult(
                    node_id=nid,
                    name=node_cfg.name,
                    output=out.data.get(node_cfg.output_key, "") if out.success else "",
                    success=out.success,
                    error=out.error,
                )
                if not out.success:
                    return PipelineRunResult(
                        success=False,
                        node_results=list(node_results.values()),
                        error=f"Node '{node_cfg.name}' failed: {out.error}",
                    )
                if nid == config.exit_node:
                    final_output = out.data.get(node_cfg.output_key, "")

        return PipelineRunResult(
            success=True,
            final_output=final_output,
            node_results=list(node_results.values()),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_input(
    node_id: str,
    results: dict[str, NodeOutput],
    initial_input: dict,
    graph: AgentGraph,
) -> NodeInput:
    """Mirror of GraphRunner._build_node_input for use in pipeline_manager."""
    if node_id == graph._entry:
        return NodeInput(node_id=node_id, data=dict(initial_input))

    parent_edges = [e for e in graph._edges if e.to_node == node_id]
    merged: dict = {}
    for edge in parent_edges:
        parent_data = results[edge.from_node].data
        if edge.data_map:
            for from_key, to_key in edge.data_map.items():
                if from_key in parent_data:
                    merged[to_key] = parent_data[from_key]
        else:
            merged.update(parent_data)
    return NodeInput(node_id=node_id, data=merged)
