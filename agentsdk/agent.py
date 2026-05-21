from __future__ import annotations
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, ConfigDict
from agentsdk.exceptions import LLMAuthError
from agentsdk.llm import LLMProvider, ToolSchema
from agentsdk.messages import AIMessage, Memory, MessageHistory, ToolCall
from agentsdk.tools.base import BaseTool
from agentsdk.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from agentsdk.persistence.session import SessionManager


# ---------------------------------------------------------------------------
# AgentConfig
# ---------------------------------------------------------------------------


class AgentConfig(BaseModel):
    """Immutable configuration for an Agent instance.

    Attributes:
        name: Human-readable agent name used in verbose output and tracing.
        system_prompt: Injected as the first SystemMessage for every new session.
        max_iterations: Hard stop preventing infinite tool-call loops. Default 10.
        max_tokens: Forwarded to LLMProvider.complete() on every call. Default 1024.
        tools_enabled: When False, tool schemas are withheld even if registered.
        verbose: Print each iteration's thought and tool calls to stdout.

    Example::

        config = AgentConfig(
            name="MyAgent",
            system_prompt="You are a helpful assistant.",
            max_iterations=5,
            verbose=True,
        )
    """

    model_config = ConfigDict(frozen=True)

    name: str
    """Human-readable agent name (used in verbose output and tracing)."""

    system_prompt: str
    """Injected as the first SystemMessage for every new session."""

    max_iterations: int = 10
    """Hard stop — prevents infinite tool-call loops."""

    max_tokens: int = 1024
    """Forwarded to LLMProvider.complete() on every call."""

    tools_enabled: bool = True
    """When False, tool schemas are withheld from the LLM even if tools are registered."""

    verbose: bool = False
    """Print each iteration's thought and tool calls to stdout (dev convenience)."""


# ---------------------------------------------------------------------------
# StepResult
# ---------------------------------------------------------------------------


class StepResult(BaseModel):
    """Snapshot of one ReAct iteration."""

    model_config = ConfigDict(frozen=True)

    iteration: int
    thought: str
    """Raw content of the AIMessage produced this step."""

    tool_calls: list[ToolCall]
    """Tool calls the model requested this step (empty if none)."""

    stop_reason: str
    """Forwarded from LLMResponse.stop_reason."""

    is_final: bool
    """True when this step caused the loop to terminate cleanly."""


# ---------------------------------------------------------------------------
# AgentResult
# ---------------------------------------------------------------------------


class AgentResult(BaseModel):
    """Full output of a single Agent.run() invocation."""

    model_config = ConfigDict(frozen=True)

    output: str
    """Final assistant message content."""

    steps: list[StepResult]
    """Ordered trace of every ReAct iteration."""

    total_input_tokens: int
    total_output_tokens: int

    stopped_by: str
    """Why the loop ended: ``end_turn`` | ``max_iterations`` | ``error``."""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class Agent:
    """Runs a ReAct agent loop using an LLM provider and optional tools.

    Args:
        config: AgentConfig with name, system prompt, and settings.
        llm: Any LLMProvider implementation — use GroqProvider.
        tools: Optional flat list of BaseTool instances.
        memory: Optional Memory backend (legacy; prefer session_manager).
        registry: Optional ToolRegistry — merged with tools if both provided.
        session_manager: Optional SessionManager for persistent sessions.

    Example::

        llm = GroqProvider(api_key="...")
        config = AgentConfig(name="MyAgent", system_prompt="You are helpful.")
        agent = Agent(config=config, llm=llm)
        result = await agent.run("What is 2 + 2?")
    """

    def __init__(
        self,
        config: AgentConfig,
        llm: LLMProvider,
        tools: list[BaseTool] | None = None,
        memory: Memory | None = None,
        registry: ToolRegistry | None = None,
        session_manager: SessionManager | None = None,
    ) -> None:
        self.config = config
        self._llm = llm
        self._memory = memory
        self._session_manager = session_manager
        self._tools: list[BaseTool] = list(tools or [])
        if registry is not None:
            self._tools.extend(registry.all())
        # O(1) lookup by tool name during dispatch
        self._tool_map: dict[str, BaseTool] = {t.schema.name: t for t in self._tools}
        # Optional async streaming callback: (event_type: str, data: dict) -> None
        # Set before calling run() to receive per-step events for WebSocket streaming.
        self._step_callback: Any | None = None

    # ------------------------------------------------------------------
    # Core run loop
    # ------------------------------------------------------------------

    async def run(
        self,
        user_input: str,
        session_id: str | None = None,
    ) -> AgentResult:
        """Execute the ReAct loop for *user_input* and return a full trace.

        Parameters
        ----------
        user_input:
            The human message that starts this turn.
        session_id:
            When provided alongside a ``Memory`` backend, the conversation
            is loaded before running and persisted afterwards.
        """
        # ── 1. Load or create history ──────────────────────────────────────
        if self._session_manager and session_id:
            history = await self._session_manager.load_history(session_id)
        elif self._memory and session_id:
            history = await self._memory.load(session_id)
        else:
            history = MessageHistory()

        # Inject system prompt only for brand-new sessions.
        if len(history) == 0:
            history.add_system(self.config.system_prompt)

        # Extension point: subclasses (e.g. BusAwareAgent) inject context here.
        await self._pre_run_hook(history)

        history.add_human(user_input)

        # ── 2. Prepare tool schemas ────────────────────────────────────────
        tool_schemas: list[ToolSchema] | None = None
        if self.config.tools_enabled and self._tools:
            tool_schemas = [t.schema for t in self._tools]

        # ── 3. ReAct loop ──────────────────────────────────────────────────
        steps: list[StepResult] = []
        total_input = 0
        total_output = 0
        stopped_by = "max_iterations"
        output = ""

        try:
            for iteration in range(1, self.config.max_iterations + 1):
                response = await self._llm.complete(
                    history,
                    tools=tool_schemas,
                    max_tokens=self.config.max_tokens,
                )

                total_input += response.input_tokens
                total_output += response.output_tokens

                ai_message: AIMessage = response.message
                history.add(ai_message)

                has_tool_calls = bool(ai_message.tool_calls)
                is_final = response.stop_reason == "end_turn" and not has_tool_calls

                step = StepResult(
                    iteration=iteration,
                    thought=ai_message.content,
                    tool_calls=list(ai_message.tool_calls),
                    stop_reason=response.stop_reason,
                    is_final=is_final,
                )
                steps.append(step)

                if self.config.verbose:
                    snippet = ai_message.content[:120].replace("\n", " ")
                    print(
                        f"[{self.config.name}] iter={iteration}"
                        f" stop={response.stop_reason}"
                        f" thought={snippet!r}"
                    )
                    for tc in ai_message.tool_calls:
                        print(f"  → tool_call: {tc.name}({tc.arguments})")

                # ── streaming callback: step + tool_call events ────────────
                if self._step_callback is not None:
                    await self._step_callback("step", {
                        "iteration": iteration,
                        "thought": ai_message.content,
                        "stop_reason": response.stop_reason,
                    })
                    for tc in ai_message.tool_calls:
                        await self._step_callback("tool_call", {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        })

                # ── clean exit ─────────────────────────────────────────────
                if is_final:
                    output = ai_message.content
                    stopped_by = "end_turn"
                    break

                # ── tool dispatch ──────────────────────────────────────────
                if has_tool_calls:
                    for tc in ai_message.tool_calls:
                        result_content, is_error = await self._dispatch_tool(tc)

                        if self.config.verbose:
                            status = "ERROR" if is_error else "OK"
                            print(f"  ← tool_result [{status}]: {result_content[:120]!r}")

                        history.add_tool_result(
                            tool_call_id=tc.id,
                            content=result_content,
                            is_error=is_error,
                        )

                        # ── streaming callback: tool_result event ─────────
                        if self._step_callback is not None:
                            await self._step_callback("tool_result", {
                                "name": tc.name,
                                "result": result_content[:2000],
                                "is_error": is_error,
                            })

                # If stop_reason is "max_tokens" or another non-final reason
                # with no tool calls, the loop continues to let the model
                # recover in the next iteration.

        except LLMAuthError:
            raise  # auth errors are not recoverable — propagate to caller
        except Exception as exc:
            stopped_by = "error"
            output = str(exc)
            if self.config.verbose:
                print(f"[{self.config.name}] ERROR: {exc}")
        # Grab the last thought as output when the loop was exhausted.
        if stopped_by == "max_iterations" and steps:
            output = steps[-1].thought

        # ── 4. Persist history ─────────────────────────────────────────────
        if self._session_manager and session_id:
            await self._session_manager.save_history(
                session_id,
                history,
                iteration=len(steps),
                metadata={"stopped_by": stopped_by},
            )
        if self._memory and session_id:
            await self._memory.save(session_id, history)

        # ── 5. Streaming final event ───────────────────────────────────────
        if self._step_callback is not None:
            await self._step_callback("final", {
                "output": output,
                "steps": len(steps),
                "tokens": {"input": total_input, "output": total_output},
                "stopped_by": stopped_by,
            })

        return AgentResult(
            output=output,
            steps=steps,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            stopped_by=stopped_by,
        )

    # ------------------------------------------------------------------
    # Convenience wrapper
    # ------------------------------------------------------------------

    async def chat(self, user_input: str, session_id: str = "default") -> str:
        """Single-call interface — returns just the final response string."""
        result = await self.run(user_input, session_id)
        return result.output

    # ------------------------------------------------------------------
    # Extension hooks
    # ------------------------------------------------------------------

    async def _pre_run_hook(self, history: MessageHistory) -> None:
        """Called after system-prompt injection, before the user message is added.

        Override in subclasses to inject additional context into *history*
        before the ReAct loop starts.  The base implementation is a no-op.
        """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _dispatch_tool(self, tc: ToolCall) -> tuple[str, bool]:
        """Execute one tool call and return (result_content, is_error)."""
        tool = self._tool_map.get(tc.name)
        if tool is None:
            return f"Tool not found: {tc.name}", True
        try:
            content = await tool.execute(**tc.arguments)
            return content, False
        except Exception as exc:  # noqa: BLE001
            return str(exc), True
