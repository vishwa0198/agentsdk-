# Product Hunt post

## Tagline (60 chars max)
Build AI agents in Python — tools, memory, multi-agent

## Description (260 chars max)
agentsdk is an open-source Python SDK for building production-grade AI agents.
ReAct loop, @tool decorator, multi-agent pipelines, persistent memory,
OpenTelemetry tracing, and a scaffold-agent CLI. Groq-powered, PyPI-ready.

---

## First comment (maker comment — this is what gets upvotes)

Hey PH! 👋 I'm Vishwa, a full-stack dev from Chennai.

I built agentsdk because every agent framework I tried was either
too opinionated or too complex to extend. I wanted something that
felt like writing normal Python.

Here's what it does:

**@tool decorator** — define a tool in 3 lines, schema auto-generated from type hints
**ReAct loop** — think → act → observe, with parallel tool calls in one iteration
**Multi-agent** — DAG pipelines + async message bus for agent delegation
**RAG memory** — ChromaDB vector store, semantic + recency hybrid retrieval
**Persistent sessions** — checkpoint, resume, and fork any conversation
**OTel tracing** — every LLM call and tool execution is traced
**CLI** — `scaffold-agent new myproject` gets you running in 60 seconds

It's live on PyPI: `pip install agentsdk-py`
Docs: https://vishwa0198.github.io/agentsdk
GitHub: https://github.com/vishwa0198/agentsdk

Would love feedback on the tool system and multi-agent API — those
were the hardest parts to design. AMA!

---

## Gallery images needed (brief for a designer or AI image gen)

**Image 1 — Terminal screenshot**
`scaffold-agent new myproject` running in a dark terminal with rich tree output
showing the generated project structure. Font: JetBrains Mono. Background: #0d0d14.

**Image 2 — Code snippet**
Side-by-side: left = raw OpenAI function spec (20 lines of JSON),
right = agentsdk @tool decorator (3 lines). Caption: "Same result. Less code."

**Image 3 — Architecture diagram**
Horizontal flow on dark background:
User message → Agent loop (ReAct) → Tools (parallel) → RAG Memory → OTel Trace → Response
Each box a rounded card with a small icon. Accent colour: #7c6af7.

**Image 4 — Web UI screenshot**
The chat interface with the ToolCallTrace panel open on the right,
showing a fibonacci tool call expanding in real time.

---

## Links
- PyPI: https://pypi.org/project/agentsdk-py/
- GitHub: https://github.com/vishwa0198/agentsdk
- Docs: https://vishwa0198.github.io/agentsdk

## Category
Developer Tools

## Topics
Python, AI, Open Source, Developer Tools, LLM
