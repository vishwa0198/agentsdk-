"""tests/test_pipeline.py

Unit tests for the pipeline manager and data models.
All tests are offline — no real Groq API calls are made.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import (
    PipelineConfig,
    PipelineEdgeConfig,
    PipelineNodeConfig,
    PipelineRunResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(id: str, name: str, *, is_entry=False, is_exit=False) -> PipelineNodeConfig:
    return PipelineNodeConfig(
        id=id,
        name=name,
        system_prompt=f"You are {name}.",
        model="llama-3.1-8b-instant",
        max_iterations=2,
        input_key="input",
        output_key="output",
        position={"x": 0.0, "y": 0.0},
    )


def _pipeline(
    nodes: list[PipelineNodeConfig],
    edges: list[PipelineEdgeConfig] | None = None,
    entry: str | None = None,
    exit_: str | None = None,
) -> PipelineConfig:
    pid = str(uuid.uuid4())[:8]
    return PipelineConfig(
        id=pid,
        name="Test Pipeline",
        nodes=nodes,
        edges=edges or [],
        entry_node=entry or (nodes[0].id if nodes else None),
        exit_node=exit_ or (nodes[-1].id if nodes else None),
    )


# ---------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------

class TestPipelineModels:
    def test_node_defaults(self):
        n = PipelineNodeConfig(id="n1", name="Researcher")
        assert n.max_iterations == 5
        assert n.input_key == "input"
        assert n.output_key == "output"
        assert n.model == "llama-3.1-8b-instant"

    def test_edge_default_data_map(self):
        e = PipelineEdgeConfig(from_node="a", to_node="b")
        assert e.data_map == {}

    def test_pipeline_serialise_roundtrip(self):
        nodes = [_node("a", "A"), _node("b", "B")]
        cfg = _pipeline(nodes, [PipelineEdgeConfig(from_node="a", to_node="b")])
        raw = cfg.model_dump_json()
        restored = PipelineConfig.model_validate_json(raw)
        assert restored.id == cfg.id
        assert len(restored.nodes) == 2
        assert len(restored.edges) == 1

    def test_pipeline_empty_nodes_valid(self):
        cfg = PipelineConfig(id="x", name="empty")
        assert cfg.nodes == []
        assert cfg.entry_node is None


# ---------------------------------------------------------------------------
# PipelineManager — persistence
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_pipeline_manager(tmp_path, monkeypatch):
    """PipelineManager writing to a temp dir instead of .agentsdk/pipelines."""
    import pipeline_manager as pm_module
    monkeypatch.setattr(pm_module, "_PIPELINES_DIR", tmp_path / "pipelines")
    from pipeline_manager import PipelineManager
    return PipelineManager()


@pytest.mark.edge
class TestPipelineManagerPersistence:
    def test_save_and_load(self, tmp_pipeline_manager):
        mgr = tmp_pipeline_manager
        cfg = _pipeline([_node("a", "A")])
        mgr.save(cfg)
        loaded = mgr.load(cfg.id)
        assert loaded is not None
        assert loaded.id == cfg.id
        assert loaded.name == cfg.name

    def test_load_nonexistent_returns_none(self, tmp_pipeline_manager):
        assert tmp_pipeline_manager.load("does-not-exist") is None

    def test_list_all_empty(self, tmp_pipeline_manager):
        assert tmp_pipeline_manager.list_all() == []

    def test_list_all_sorted_by_name(self, tmp_pipeline_manager):
        mgr = tmp_pipeline_manager
        for name in ["Zeta", "Alpha", "Mu"]:
            cfg = PipelineConfig(id=name.lower(), name=name)
            mgr.save(cfg)
        names = [p.name for p in mgr.list_all()]
        assert names == sorted(names, key=str.lower)

    def test_delete_existing(self, tmp_pipeline_manager):
        mgr = tmp_pipeline_manager
        cfg = _pipeline([_node("a", "A")])
        mgr.save(cfg)
        assert mgr.delete(cfg.id) is True
        assert mgr.load(cfg.id) is None

    def test_delete_nonexistent_returns_false(self, tmp_pipeline_manager):
        assert tmp_pipeline_manager.delete("ghost") is False

    def test_overwrite_pipeline(self, tmp_pipeline_manager):
        mgr = tmp_pipeline_manager
        cfg = _pipeline([_node("a", "A")])
        mgr.save(cfg)
        cfg2 = PipelineConfig(id=cfg.id, name="Updated Name")
        mgr.save(cfg2)
        loaded = mgr.load(cfg.id)
        assert loaded.name == "Updated Name"

    def test_corrupted_json_skipped_in_list(self, tmp_pipeline_manager, tmp_path, monkeypatch):
        import pipeline_manager as pm_module
        pl_dir = tmp_path / "pipelines"
        pl_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(pm_module, "_PIPELINES_DIR", pl_dir)
        (pl_dir / "bad.json").write_text("not json", encoding="utf-8")
        from pipeline_manager import PipelineManager
        mgr = PipelineManager()
        assert mgr.list_all() == []


# ---------------------------------------------------------------------------
# PipelineManager — execution (mocked agents)
# ---------------------------------------------------------------------------

def _make_agent_result(output: str):
    from agentsdk.agent import AgentResult, StepResult
    return AgentResult(
        output=output,
        steps=[StepResult(iteration=1, thought=output, tool_calls=[], stop_reason="end_turn", is_final=True)],
        total_input_tokens=10,
        total_output_tokens=5,
        stopped_by="end_turn",
    )


@pytest.mark.asyncio
@pytest.mark.edge
class TestPipelineManagerRun:
    async def _run_pipeline(self, tmp_pipeline_manager, nodes, edges=None, entry=None, exit_=None, input_="hello"):
        """Helper that mocks Agent.run() and runs the pipeline."""
        cfg = _pipeline(nodes, edges, entry, exit_)
        with patch("pipeline_manager.Agent") as MockAgent:
            inst = AsyncMock()
            inst.run = AsyncMock(return_value=_make_agent_result("mocked output"))
            MockAgent.return_value = inst
            return await tmp_pipeline_manager.run(cfg, input_)

    async def test_single_node_success(self, tmp_pipeline_manager):
        nodes = [_node("n1", "Solo")]
        result = await self._run_pipeline(tmp_pipeline_manager, nodes)
        assert result.success
        assert result.final_output == "mocked output"
        assert len(result.node_results) == 1
        assert result.node_results[0].node_id == "n1"

    async def test_two_node_pipeline(self, tmp_pipeline_manager):
        nodes = [_node("n1", "First"), _node("n2", "Second")]
        edges = [PipelineEdgeConfig(from_node="n1", to_node="n2")]
        result = await self._run_pipeline(tmp_pipeline_manager, nodes, edges=edges, entry="n1", exit_="n2")
        assert result.success
        assert len(result.node_results) == 2

    async def test_no_nodes_returns_error(self, tmp_pipeline_manager):
        cfg = PipelineConfig(id="x", name="empty")
        result = await tmp_pipeline_manager.run(cfg, "hi")
        assert not result.success
        assert "no nodes" in (result.error or "").lower()

    async def test_no_entry_returns_error(self, tmp_pipeline_manager):
        cfg = PipelineConfig(id="x", name="e", nodes=[_node("n1", "A")])
        result = await tmp_pipeline_manager.run(cfg, "hi")
        assert not result.success
        assert "entry" in (result.error or "").lower()

    async def test_no_exit_returns_error(self, tmp_pipeline_manager):
        cfg = PipelineConfig(id="x", name="e", nodes=[_node("n1", "A")], entry_node="n1")
        result = await tmp_pipeline_manager.run(cfg, "hi")
        assert not result.success
        assert "exit" in (result.error or "").lower()

    async def test_failing_node_aborts(self, tmp_pipeline_manager):
        """When a node fails, run() returns early with the error."""
        from agentsdk.agent import AgentResult, StepResult
        nodes = [_node("n1", "Failing"), _node("n2", "Never Reached")]
        edges = [PipelineEdgeConfig(from_node="n1", to_node="n2")]
        failed_result = AgentResult(
            output="something went wrong",
            steps=[StepResult(iteration=1, thought="error", tool_calls=[], stop_reason="error", is_final=True)],
            total_input_tokens=5,
            total_output_tokens=2,
            stopped_by="error",
        )
        cfg = _pipeline(nodes, edges, entry="n1", exit_="n2")
        with patch("pipeline_manager.Agent") as MockAgent:
            inst = AsyncMock()
            inst.run = AsyncMock(return_value=failed_result)
            MockAgent.return_value = inst
            result = await tmp_pipeline_manager.run(cfg, "hi")
        assert not result.success
        assert "Failing" in (result.error or "")
