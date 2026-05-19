"""agentsdk/observability/middleware.py

TracedAgent — Agent subclass with per-step and per-tool OTel spans.
print_trace  — human-readable TraceContext summary.
"""

from __future__ import annotations

from datetime import datetime, timezone

from opentelemetry import trace as otel_trace
from opentelemetry.trace import StatusCode

from agentsdk.agent import Agent, AgentConfig, AgentResult, StepResult
from agentsdk.llm import LLMProvider, ToolSchema
from agentsdk.messages import AIMessage, MessageHistory
from agentsdk.observability.tracer import AgentSpan, SDKTracer, TraceContext
from agentsdk.tools.base import BaseTool
from agentsdk.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# TracedAgent
# ---------------------------------------------------------------------------


class TracedAgent(Agent):
    """Agent subclass that wraps the entire ReAct loop with OTel spans.

    Span hierarchy per ``run()`` call::

        agent.run
          agent.step  (one per iteration)
            llm.complete  (emitted by TracedLLMProvider if used)
            tool.execute  (one per tool call, zero or more)

    The override returns ``tuple[AgentResult, TraceContext]`` instead of
    just ``AgentResult``.

    Parameters
    ----------
    tracer:
        An ``SDKTracer`` instance — must be the same one given to
        ``TracedLLMProvider`` if you want LLM spans to be nested correctly.
    All other parameters are forwarded to ``Agent.__init__``.
    """

    def __init__(
        self,
        config: AgentConfig,
        llm: LLMProvider,
        tracer: SDKTracer,
        tools: list[BaseTool] | None = None,
        memory=None,
        registry: ToolRegistry | None = None,
        session_manager=None,
    ) -> None:
        super().__init__(
            config=config,
            llm=llm,
            tools=tools,
            memory=memory,
            registry=registry,
            session_manager=session_manager,
        )
        self._tracer = tracer

    # ------------------------------------------------------------------
    # Traced run loop
    # ------------------------------------------------------------------

    async def run(  # type: ignore[override]
        self,
        user_input: str,
        session_id: str | None = None,
    ) -> tuple[AgentResult, TraceContext]:
        """Execute the ReAct loop with OTel tracing.

        Returns
        -------
        (AgentResult, TraceContext)
            The normal result plus aggregated trace metadata for this run.
        """
        started_at = datetime.now(timezone.utc)
        span_names: list[str] = []
        trace_id = ""
        total_llm_calls = 0
        total_tool_calls = 0
        total_input = 0
        total_output = 0

        # These are set inside the root span; Python has function scope so
        # they are accessible after the `with` block closes.
        steps: list[StepResult] = []
        stopped_by = "max_iterations"
        output = ""

        with self._tracer.span("agent.run") as root_span:
            span_names.append("agent.run")
            root_span.set_attribute(AgentSpan.AGENT_NAME, self.config.name)
            if session_id:
                root_span.set_attribute(AgentSpan.AGENT_SESSION, session_id)

            # Capture the OTel trace ID from the current span context.
            otel_ctx = otel_trace.get_current_span().get_span_context()
            if otel_ctx and otel_ctx.is_valid:
                trace_id = format(otel_ctx.trace_id, "032x")

            # ── 1. Load or create history ──────────────────────────────────
            if self._session_manager and session_id:
                history = await self._session_manager.load_history(session_id)
            elif self._memory and session_id:
                history = await self._memory.load(session_id)
            else:
                history = MessageHistory()

            if len(history) == 0:
                history.add_system(self.config.system_prompt)

            await self._pre_run_hook(history)
            history.add_human(user_input)

            # ── 2. Prepare tool schemas ────────────────────────────────────
            tool_schemas: list[ToolSchema] | None = None
            if self.config.tools_enabled and self._tools:
                tool_schemas = [t.schema for t in self._tools]

            # ── 3. ReAct loop ──────────────────────────────────────────────
            try:
                for iteration in range(1, self.config.max_iterations + 1):
                    with self._tracer.span("agent.step") as step_span:
                        span_names.append("agent.step")
                        step_span.set_attribute(AgentSpan.AGENT_ITERATION, iteration)

                        response = await self._llm.complete(
                            history,
                            tools=tool_schemas,
                            max_tokens=self.config.max_tokens,
                        )
                        total_llm_calls += 1
                        total_input += response.input_tokens
                        total_output += response.output_tokens

                        ai_message: AIMessage = response.message
                        history.add(ai_message)

                        has_tool_calls = bool(ai_message.tool_calls)
                        is_final = (
                            response.stop_reason == "end_turn" and not has_tool_calls
                        )

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

                        # ── clean exit ─────────────────────────────────────
                        if is_final:
                            output = ai_message.content
                            stopped_by = "end_turn"
                            break

                        # ── tool dispatch ──────────────────────────────────
                        if has_tool_calls:
                            for tc in ai_message.tool_calls:
                                with self._tracer.span("tool.execute") as tool_span:
                                    span_names.append("tool.execute")
                                    tool_span.set_attribute(AgentSpan.TOOL_NAME, tc.name)
                                    total_tool_calls += 1

                                    result_content, is_error = await self._dispatch_tool(tc)

                                    tool_span.set_attribute(
                                        AgentSpan.TOOL_SUCCESS, not is_error
                                    )
                                    if is_error:
                                        tool_span.set_attribute(
                                            AgentSpan.TOOL_ERROR, result_content
                                        )

                                if self.config.verbose:
                                    status = "ERROR" if is_error else "OK"
                                    print(
                                        f"  ← tool_result [{status}]: {result_content[:120]!r}"
                                    )

                                history.add_tool_result(
                                    tool_call_id=tc.id,
                                    content=result_content,
                                    is_error=is_error,
                                )

            except Exception as exc:
                stopped_by = "error"
                output = str(exc)
                root_span.record_exception(exc)
                root_span.set_status(StatusCode.ERROR)
                if self.config.verbose:
                    print(f"[{self.config.name}] ERROR: {exc}")

            # Grab the last thought when the loop was exhausted.
            if stopped_by == "max_iterations" and steps:
                output = steps[-1].thought

            root_span.set_attribute(AgentSpan.AGENT_STOPPED_BY, stopped_by)

            # ── 4. Persist history ─────────────────────────────────────────
            if self._session_manager and session_id:
                await self._session_manager.save_history(
                    session_id,
                    history,
                    iteration=len(steps),
                    metadata={"stopped_by": stopped_by},
                )
            elif self._memory and session_id:
                await self._memory.save(session_id, history)

        # Root span has now closed; build result objects.
        finished_at = datetime.now(timezone.utc)

        result = AgentResult(
            output=output,
            steps=steps,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            stopped_by=stopped_by,
        )

        trace_ctx = TraceContext(
            trace_id=trace_id,
            agent_name=self.config.name,
            session_id=session_id,
            spans=span_names,
            started_at=started_at,
            finished_at=finished_at,
            total_llm_calls=total_llm_calls,
            total_tool_calls=total_tool_calls,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
        )

        return result, trace_ctx


# ---------------------------------------------------------------------------
# print_trace — human-readable TraceContext summary
# ---------------------------------------------------------------------------

_WIDTH = 45


def print_trace(ctx: TraceContext) -> None:
    """Print a formatted summary of a ``TraceContext`` to stdout.

    Example output::

        ╔══ Trace: MyAgent ══════════════════════════
        ║  Session     : user-001
        ║  Trace ID    : 4bf92f3577b34da6a3ce929d0e0e4736
        ║  Duration    : 843ms
        ║  LLM calls   : 2
        ║  Tool calls  : 1
        ║  Tokens      : 312 in / 48 out
        ╚═════════════════════════════════════════════
    """
    duration_ms = 0
    if ctx.finished_at is not None:
        duration_ms = int(
            (ctx.finished_at - ctx.started_at).total_seconds() * 1000
        )

    header_label = f"Trace: {ctx.agent_name} "
    pad = max(0, _WIDTH - len(header_label) - 4)  # 4 = "╔══ " prefix chars
    print(f"╔══ {header_label}{'═' * pad}")
    print(f"║  Session     : {ctx.session_id or '(none)'}")
    print(f"║  Trace ID    : {ctx.trace_id or '(none)'}")
    print(f"║  Duration    : {duration_ms}ms")
    print(f"║  LLM calls   : {ctx.total_llm_calls}")
    print(f"║  Tool calls  : {ctx.total_tool_calls}")
    print(f"║  Tokens      : {ctx.total_input_tokens} in / {ctx.total_output_tokens} out")
    print(f"╚{'═' * (_WIDTH + 1)}")
