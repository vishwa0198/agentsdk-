# Hacker News — Show HN post

## Title
Show HN: agentsdk – open-source Python SDK for building AI agents (ReAct, tools, multi-agent)

## Body

I spent the last few weeks building agentsdk from scratch —
a lightweight Python SDK for production-grade AI agents.

What it does:
- ReAct loop with parallel tool calls in a single iteration
- @tool decorator — JSON schema auto-generated from type hints, no boilerplate
- Multi-agent DAG pipelines + async message bus for mid-loop delegation
- ChromaDB RAG memory (semantic + recency hybrid)
- Persistent sessions with checkpoint, resume, and fork
- OpenTelemetry tracing on every LLM call and tool execution
- scaffold-agent CLI — new project in 60 seconds
- Docker-sandboxed code execution (no network, 128MB cap)

It's Groq-powered by default (free tier, fast) with an Anthropic stub
ready to swap in. Pure Python, no heavy dependencies beyond Pydantic v2.

    pip install agentsdk-py

GitHub: https://github.com/vishwa0198/agentsdk
Docs: https://vishwa0198.github.io/agentsdk

Happy to answer questions about the design decisions — especially
the tool schema auto-generation and the multi-agent message bus,
which were the trickiest parts to get right.

---

## Post timing
Tuesday or Wednesday, 9am–11am US Eastern (7:30pm–9:30pm IST).
This is the highest-traffic window for Show HN posts.

---

## Prepared answers for expected questions

**Q: How is this different from LangChain?**
A: Smaller surface area, no hidden abstractions, you own the agent loop.
LangChain has 800+ integrations; agentsdk has 14 tools and a clean protocol
to add more. The @tool decorator + ToolRegistry is 200 lines total. You can
read the entire core in an afternoon.

**Q: Why Groq instead of OpenAI?**
A: Free tier, fast inference, llama-3.3-70b is capable enough for dev/test.
AnthropicProvider stub is already in llm.py — one-line swap for production.
Nothing in the SDK is Groq-specific; any provider implementing the
LLMProvider protocol works.

**Q: Is it production ready?**
A: Core loop and tool system yes. The web UI is dev-grade.
Docker sandbox, OTel tracing, and session persistence are production patterns.
I'd use it in a production internal tool today; I'd evaluate carefully before
exposing it to untrusted user input.

**Q: How does the RAG memory compare to just passing full history?**
A: Full history hits token limits after ~20 turns. RAGMemory keeps last 5
messages (recency) + top 5 semantic matches (relevance) — agents stay
context-aware without blowing up the context window. On a 100-turn session
this saves ~60% of input tokens vs naive full-history.

**Q: Does it support streaming?**
A: Yes — the WebSocket endpoint in the web UI streams step/tool_call/
tool_result/final events in real time. The core SDK has a step_callback
hook you can wire to any streaming transport.

**Q: What's the license?**
A: MIT. Build whatever you want.
