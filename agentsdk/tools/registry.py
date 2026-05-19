"""agentsdk/tools/registry.py

Central tool store — register, look up, and enumerate tools by name.
"""

from __future__ import annotations

from agentsdk.llm import ToolSchema
from agentsdk.tools.base import BaseTool


class ToolRegistry:
    """A named collection of BaseTool instances.

    Pass a registry to ``Agent(registry=...)`` to make all its tools
    available to the agent loop without building a flat list manually.

    Example::

        registry = ToolRegistry()
        registry.register(my_tool)
        agent = Agent(config=config, llm=llm, registry=registry)
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """Add *tool* to the registry.

        Raises
        ------
        ValueError
            If a tool with the same name is already registered.
        """
        name = tool.schema.name
        if name in self._tools:
            raise ValueError(
                f"Tool '{name}' is already registered. "
                "Use a different name or deregister the existing tool first."
            )
        self._tools[name] = tool

    def register_many(self, tools: list[BaseTool]) -> None:
        """Register multiple tools in order; raises on the first collision."""
        for t in tools:
            self.register(t)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get(self, name: str) -> BaseTool | None:
        """Return the tool named *name*, or ``None`` if not found."""
        return self._tools.get(name)

    def all(self) -> list[BaseTool]:
        """Return every registered tool (insertion order preserved)."""
        return list(self._tools.values())

    def schemas(self) -> list[ToolSchema]:
        """Return just the :class:`ToolSchema` for every registered tool.

        This is the list you pass to ``LLMProvider.complete(tools=...)``.
        """
        return [t.schema for t in self._tools.values()]

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __contains__(self, name: str) -> bool:
        """Support ``if "tool_name" in registry`` checks."""
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:  # pragma: no cover
        names = list(self._tools.keys())
        return f"ToolRegistry(tools={names})"
