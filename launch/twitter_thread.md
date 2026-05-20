# Twitter/X thread

---

**Tweet 1 — Hook**

I spent weeks building an AI agent SDK from scratch in Python.

Here's everything I learned about ReAct loops, tool schemas,
and multi-agent systems 🧵

---

**Tweet 2 — The problem**

Every agent framework I tried had the same issue:
too much magic, not enough Python.

I wanted to understand what's actually happening when an agent
"thinks" — so I built it from scratch.

---

**Tweet 3 — The loop**

An AI agent is just a loop:

1. Give the LLM your message + available tools
2. LLM either answers OR calls a tool
3. Run the tool, give result back to LLM
4. Repeat until done

That's it. The whole thing.

---

**Tweet 4 — The @tool decorator**

The best DX decision I made: the @tool decorator

```python
@tool
async def search_web(query: str) -> str:
    """Search the web and return results."""
    ...
```

JSON schema auto-generated from type hints.
No boilerplate. The LLM gets exactly what it needs.

---

**Tweet 5 — Multi-agent**

The hardest part: agents talking to each other MID-run

Not a static pipeline — actual delegation.

Agent A is thinking → realizes it needs help →
calls ask_agent("calculator", "123 * 456") →
gets 56088 back → continues

Built an async message bus with request/reply for this.

---

**Tweet 6 — RAG memory**

Problem: full conversation history hits token limits after ~20 turns

Solution: hybrid RAG memory
- Keep last 5 messages (recency)
- Fetch top 5 semantically relevant past messages
- ChromaDB + all-MiniLM-L6-v2 embeddings

Agents stay context-aware across 100+ turn sessions.

---

**Tweet 7 — CTA**

It's live on PyPI:

```
pip install agentsdk-py
scaffold-agent new myproject
```

GitHub: github.com/vishwa0198/agentsdk
Docs: vishwa0198.github.io/agentsdk

14 built-in tools, multi-agent pipelines, persistent sessions,
OTel tracing, and a web UI. All open source. 🚀

---

## Posting notes

- Post as a thread (reply-chain), not separate tweets
- Tweet 1 goes out first — wait 10 min, then reply with 2, 3... 7 in sequence
- Pin Tweet 1 to your profile on launch day
- Add a code screenshot image to Tweet 4 (use carbon.now.sh)
- Engage with every reply within the first 2 hours — the algorithm rewards it
- Repost at 6pm your timezone if momentum slows (quote-tweet, not raw repost)
