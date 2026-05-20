# How I built an AI agent SDK from scratch in Python

*A walkthrough of agentsdk — ReAct loops, tool schemas, multi-agent pipelines,
and everything I learned along the way.*

**TL;DR:** I got frustrated with LangChain's complexity, so I built my own agent SDK.
Here's how it works, what I got wrong, and how you can use it.
`pip install agentsdk-py`

---

## Why I built this

I've been building LLM-powered features for about a year. Every time I reached for
LangChain or AutoGen, I hit the same wall: too much magic. I'd spend an hour tracing
through abstractions trying to understand *why* a prompt was being modified, or *where*
a tool result was being injected, only to find it was happening in some deeply nested
chain class five imports away from my code.

I also wanted to understand agent loops at a deep level. The only way I know how to
understand something is to build it. So I did.

The goal was simple: write an agent SDK that a mid-level Python developer could
read end-to-end in an afternoon. No metaclasses, no hidden state, no magic
prompt engineering. Just Python.

The result is **agentsdk** — 2,000 lines of core code, 14 built-in tools,
multi-agent pipelines, persistent sessions, OTel tracing, and a FastAPI + React
web UI. Version 0.2.0 is live on PyPI today.

---

## What an AI agent actually is

Before the code, let me explain what's actually happening when an "agent" runs.

An AI agent is a loop. That's it. Specifically, it's the **ReAct loop**
(Reasoning + Acting), and it looks like this:

1. Send the LLM your message plus a list of available tools
2. The LLM either responds with a final answer, or calls one of the tools
3. If it calls a tool, run it and send the result back to the LLM
4. Repeat until the LLM gives a final answer or you hit a max-iteration limit

Here's what that looks like in agentsdk:

```python
from agentsdk import Agent, AgentConfig
from agentsdk.llm import GroqProvider
from agentsdk.tools.builtin import DEFAULT_TOOLS

llm = GroqProvider(api_key="gsk_...")
config = AgentConfig(
    name="MyAgent",
    system_prompt="You are a helpful assistant. Use tools when needed.",
    max_iterations=10,
)
agent = Agent(config=config, llm=llm, registry=DEFAULT_TOOLS)

result = await agent.run("What is the 10th Fibonacci number?")
print(result.output)  # The first 10 Fibonacci numbers are: [0, 1, 1, 2, 3, ...]
```

The agent will call `run_python` to compute the sequence, get the result, and
wrap it in a natural language response. No prompt engineering on your part.

The power of this loop is that the LLM can chain tools. Ask it to "scrape this
URL, summarise it, and save to a file" — it'll call `scrape_webpage`, then
`write_file`, in sequence, passing results between steps automatically.

---

## The hardest design decision: the @tool decorator

Every agent framework needs to solve the same problem: LLMs need a JSON schema
to call tools, but writing that schema by hand is tedious and error-prone.

Here's what the raw OpenAI function spec looks like:

```python
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a city",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"},
                "units": {"type": "string", "enum": ["celsius", "fahrenheit"]}
            },
            "required": ["city"]
        }
    }
}]
```

That's 20 lines to describe one function. With agentsdk, it's this:

```python
from agentsdk.tools import tool

@tool
async def get_weather(city: str, units: str = "celsius") -> str:
    """Get current weather for a city."""
    ...
```

The `@tool` decorator uses `inspect.signature()` to extract parameter names and
types, maps Python type hints to JSON Schema types, uses the docstring as the
description, and infers required vs optional from whether there's a default value.

The implementation is about 80 lines of code in `agentsdk/tools/base.py`.
What I got wrong the first time: I initially designed it as a class hierarchy
(`class WeatherTool(BaseTool)`). This felt more "proper" but meant 30+ lines per
tool and made the code feel like Java. The decorator approach came from looking
at how FastAPI does route decorators — same idea, much better DX.

---

## Multi-agent: harder than it looks

Single-agent systems are relatively straightforward. Multi-agent is where things
get interesting — and tricky.

The obvious approach is a static pipeline: `Agent A → Agent B → Agent C`.
agentsdk supports this with `MultiAgentPipeline`:

```python
from agentsdk.multi_agent import MultiAgentPipeline, PipelineStep

pipeline = MultiAgentPipeline(steps=[
    PipelineStep(agent=researcher, output_key="research"),
    PipelineStep(agent=writer,    input_key="research", output_key="draft"),
    PipelineStep(agent=editor,    input_key="draft",    output_key="final"),
])
result = await pipeline.run("Write a report on quantum computing")
```

But what if Agent A is mid-loop and realises it needs to delegate to a specialist?
That's where the **async message bus** comes in.

```python
from agentsdk.multi_agent import AgentBus, BusAwareAgent

bus = AgentBus()
bus.register("calculator", calculator_agent)
bus.register("researcher", researcher_agent)

# In the main agent's tool list:
ask_agent_tool = bus.make_ask_agent_tool()

# Now the main agent can call:
# ask_agent("calculator", "What is 1234 * 5678?")
# mid-loop, get the result, and continue
```

The bus implements request/reply over `asyncio.Queue`. Each registered agent
gets its own queue; `ask_agent` sends a message and `await`s the reply before
returning control to the calling agent.

The `data_map` gotcha: in the pipeline, `output_key` on step N must match
`input_key` on step N+1. This seems obvious but I got it wrong on my first
integration test and spent 40 minutes debugging why the writer agent was
getting an empty input. The fix was adding a runtime validation check at
pipeline construction time.

---

## RAG memory: why full history doesn't scale

The naive approach to agent memory is to pass the entire conversation history
to the LLM on every turn. This works fine for 5–10 turns. After 20 turns on
`llama-3.3-70b`, you're pushing 8,000–12,000 tokens per request — expensive,
slow, and approaching context limits.

agentsdk's `RAGMemory` uses a hybrid approach:

- **Recency buffer** — always include the last 5 messages verbatim
- **Semantic search** — embed the current query with `all-MiniLM-L6-v2` and
  fetch the top 5 most semantically relevant past messages from ChromaDB

This means a 100-turn session still fits in ~2,000 tokens of context, and the
agent can recall facts from early in the conversation if they're relevant now.

```python
from agentsdk.memory import RAGMemory, VectorMemoryStore

store = VectorMemoryStore(collection_name="my-session")
memory = RAGMemory(store=store, max_messages=20)

agent = Agent(config=config, llm=llm, registry=registry, memory=memory)
```

The tricky part was the embedding step. I initially ran it synchronously,
which blocked the event loop on every message. Fixed by wrapping
`sentence_transformers.encode()` in `loop.run_in_executor()`.

---

## What I'd do differently

**Start with the persistence layer earlier.** I built SessionManager
(checkpoint + resume) in week 3, but the patterns it needed
(serialisable message history, stable session IDs) should have been
designed in week 1. Retrofitting it meant refactoring the core message
representation twice.

**asyncpg from day one.** I reached for aiosqlite because it's simpler,
then added asyncpg for PostgreSQL support later. The two have slightly
different query parameter syntax (`?` vs `$1`) which caused a subtle
cross-database bug. Design for the harder target first.

**Fill in the AnthropicProvider stub earlier.** I kept it as a `raise
NotImplementedError` for two weeks while focussing on the Groq path.
Every time I showed the code to someone they asked about OpenAI/Anthropic
support immediately. The stub communicates intent but also communicates
"this isn't done yet" — not great for first impressions.

---

## Try it

```bash
pip install agentsdk-py
scaffold-agent new myproject
cd myproject
# Add your GROQ_API_KEY to .env
python -c "
import asyncio
from agentsdk import Agent, AgentConfig
from agentsdk.llm import GroqProvider
from agentsdk.tools.builtin import DEFAULT_TOOLS
import os; from dotenv import load_dotenv; load_dotenv()

async def main():
    llm = GroqProvider(api_key=os.environ['GROQ_API_KEY'])
    agent = Agent(AgentConfig(name='demo'), llm=llm, registry=DEFAULT_TOOLS)
    result = await agent.run('What is the capital of France?')
    print(result.output)

asyncio.run(main())
"
```

- **GitHub:** https://github.com/vishwa0198/agentsdk
- **Docs:** https://vishwa0198.github.io/agentsdk
- **PyPI:** https://pypi.org/project/agentsdk-py/

If you build something with it, I'd love to see it — open a Discussion on GitHub
or ping me on X/Twitter. Questions and PRs welcome.

---

*Target: 2,000–2,500 words | Cross-post: dev.to, Hashnode, LinkedIn | Post same day as HN*
