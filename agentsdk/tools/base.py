"""agentsdk/tools/base.py

BaseTool abstract interface, FunctionTool concrete wrapper, and the @tool
decorator with automatic JSON Schema generation from Python type hints.

Import chain (no circular dependencies):
    tools/base.py → agentsdk.llm (ToolSchema)
                  → stdlib only (abc, inspect, typing, types)
"""

from __future__ import annotations

import abc
import inspect
import types as _types
import typing
from collections.abc import Awaitable, Callable
from typing import Any

from agentsdk.llm import ToolSchema


# ---------------------------------------------------------------------------
# Python type hint → JSON Schema
# ---------------------------------------------------------------------------


def python_type_to_json_schema(annotation: Any) -> dict[str, Any]:
    """Convert a single Python type hint to a JSON Schema dict.

    Handles the most common annotations used in tool signatures:
    ``str``, ``int``, ``float``, ``bool``, ``dict``, ``list[X]``,
    ``Optional[X]`` / ``X | None``.  Anything unrecognised falls back to
    ``{"type": "string"}`` so the schema is always valid.
    """
    # ── primitive scalars ──────────────────────────────────────────────────
    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is dict:
        return {"type": "object"}

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    # ── list[X] / List[X] ─────────────────────────────────────────────────
    if origin is list:
        item_schema = (
            python_type_to_json_schema(args[0]) if args else {"type": "string"}
        )
        return {"type": "array", "items": item_schema}

    # ── Union / Optional[X] / X | None ────────────────────────────────────
    # typing.Union covers Optional[X]; types.UnionType covers X | None (3.10+)
    is_union = origin is typing.Union or (
        hasattr(_types, "UnionType") and isinstance(annotation, _types.UnionType)
    )
    if is_union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return python_type_to_json_schema(non_none[0])
        # Multiple non-None branches → safe fallback
        return {"type": "string"}

    # ── fallback ───────────────────────────────────────────────────────────
    return {"type": "string"}


# ---------------------------------------------------------------------------
# BaseTool — abstract interface
# ---------------------------------------------------------------------------


class BaseTool(abc.ABC):
    """Interface every agent tool must implement.

    The agent loop calls only ``schema`` and ``execute`` — it has no
    knowledge of how a tool works internally.
    """

    @property
    @abc.abstractmethod
    def schema(self) -> ToolSchema:
        """Return the ToolSchema that describes this tool to the LLM."""
        ...

    @abc.abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Run the tool and return a plain-string result.

        Any exception raised here is caught by ``FunctionTool.execute`` and
        returned as an ``"Error: …"`` string; the agent loop records it with
        ``is_error=True``.
        """
        ...


# ---------------------------------------------------------------------------
# FunctionTool — wraps a decorated async function
# ---------------------------------------------------------------------------


class FunctionTool(BaseTool):
    """A ``BaseTool`` backed by a plain async function.

    Constructed automatically by the ``@tool`` decorator — you rarely need
    to instantiate this directly.
    """

    def __init__(
        self,
        fn: Callable[..., Awaitable[str]],
        tool_schema: ToolSchema,
    ) -> None:
        self._fn = fn
        self._schema = tool_schema

    @property
    def schema(self) -> ToolSchema:
        return self._schema

    async def execute(self, **kwargs: Any) -> str:
        """Call the wrapped function; return errors as strings."""
        try:
            return await self._fn(**kwargs)
        except Exception as exc:  # noqa: BLE001
            return f"Error: {exc}"

    def __repr__(self) -> str:  # pragma: no cover
        return f"FunctionTool(name={self._schema.name!r})"


# ---------------------------------------------------------------------------
# @tool decorator
# ---------------------------------------------------------------------------


def tool(func: Callable[..., Awaitable[str]]) -> FunctionTool:
    """Decorator that turns an async function into a FunctionTool.

    The function must have a docstring (used as the tool description) and
    type-annotated parameters (used to generate the JSON Schema).

    Args:
        func: An async function with a docstring and annotated parameters.

    Returns:
        A FunctionTool instance ready to pass to ``Agent(tools=[...])`` or
        ``ToolRegistry.register()``.

    Raises:
        ValueError: If the function has no docstring.

    Example::

        @tool
        async def add_numbers(a: int, b: int) -> str:
            \"\"\"Add two integers and return the result as a string.\"\"\"
            return str(a + b)
    """
    name = func.__name__
    description = (func.__doc__ or "").strip()
    if not description:
        raise ValueError(
            f"Tool '{name}' must have a docstring — "
            "the LLM uses it to decide when to call the tool."
        )

    sig = inspect.signature(func)
    # Resolve string annotations (from `from __future__ import annotations`)
    # to their actual type objects so python_type_to_json_schema works correctly.
    try:
        hints = typing.get_type_hints(func)
    except Exception:
        hints = {}

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue

        annotation = hints.get(param_name, param.annotation)
        param_schema = (
            python_type_to_json_schema(annotation)
            if annotation is not inspect.Parameter.empty
            else {"type": "string"}
        )
        properties[param_name] = param_schema

        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    tool_schema = ToolSchema(
        name=name,
        description=description,
        parameters={
            "type": "object",
            "properties": properties,
            "required": required,
        },
    )
    return FunctionTool(fn=func, tool_schema=tool_schema)
