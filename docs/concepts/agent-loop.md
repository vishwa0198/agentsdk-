# Agent Loop

agentsdk uses the **ReAct** (Reason + Act) pattern. Each iteration the agent:

1. **Thinks** — calls the LLM, gets an `AIMessage` (text or tool calls)
2. **Acts** — dispatches any tool calls in parallel, collects results
3. **Observes** — appends tool results to history, loops back to step 1
4. **Stops** — when `stop_reason == "end_turn"` with no pending tool calls, or `max_iterations` is reached

## AgentConfig fields

```python
from agentsdk import AgentConfig

config = AgentConfig(
    name="MyAgent",           # Used in verbose output and traces
    system_prompt="...",      # Injected once at the start of every new session
    max_iterations=10,        # Hard cap on the think→act loop (default: 10)
    max_tokens=1024,          # Token budget per LLM call (default: 1024)
    tools_enabled=True,       # Set False to run the agent without tools
    verbose=False,            # Print each step to stdout (dev convenience)
)
```

## AgentResult fields

`agent.run()` returns an `AgentResult`:

```python
result = await agent.run("What is 2 + 2?")

result.output            # str  — final assistant message
result.stopped_by        # str  — "end_turn" | "max_iterations" | "error"
result.steps             # list[StepResult] — one per iteration
result.total_input_tokens
result.total_output_tokens
```

Each `StepResult` has:

```python
step.iteration    # int — 1-based
step.thought      # str — raw AIMessage content
step.tool_calls   # list[ToolCall]
step.stop_reason  # str
step.is_final     # bool
```

## Create and run an agent

```python
import asyncio, os
from dotenv import load_dotenv
from agentsdk import Agent, AgentConfig, GroqProvider

load_dotenv()

async def main():
    agent = Agent(
        config=AgentConfig(
            name="ReasoningAgent",
            system_prompt="You are a concise reasoning assistant.",
            max_iterations=5,
            verbose=True,
        ),
        llm=GroqProvider(api_key=os.environ["GROQ_API_KEY"]),
    )

    result = await agent.run("Why is the sky blue? One sentence.")
    print(result.output)
    print(f"Stopped by: {result.stopped_by} | Steps: {len(result.steps)}")

asyncio.run(main())
```
