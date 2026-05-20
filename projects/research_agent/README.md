# Research Agent

An AI-powered research agent built on **agentsdk**. Given a topic, it fetches web pages, ingests content into vector memory for semantic retrieval, and synthesises a structured Markdown report citing all sources.

## Features

- Fetches and parses web pages with **`fetch_and_ingest`** (custom tool)
- Ingests content into **ChromaDB** for semantic retrieval mid-research
- Synthesises structured reports: Summary · Key Facts · Details · Sources
- Saves reports as `.md` files to `/tmp/research/`
- Persistent sessions — resume with `--session`
- Rich terminal UI showing each agent step in real-time

## Setup

```bash
# From the repository root
pip install -e ".[rag]"
pip install rich

# .env file with your Groq API key (already exists at repo root)
# GROQ_API_KEY=gsk_...
```

## Usage

```bash
# Run from the projects/research_agent/ directory
cd projects/research_agent

# One-shot research
python main.py "The history and impact of Python programming language"

# Interactive prompt (no argument)
python main.py

# Resume a named session for follow-up questions
python main.py --session groq-research "How does the Groq LPU architecture work"
```

## Output

```
╭───────────────────────────────────────────────────────╮
│     Research Agent — powered by agentsdk              │
╰───────────────────────────────────────────────────────╯
Topic: The history and impact of Python programming language
Session: research-4f2a9e01

Agent steps will appear below as they complete…

[ResearchAgent] iter=1 stop=tool_use thought="I'll start with Wikipedia…"
  → tool_call: fetch_and_ingest({'url': 'https://en.wikipedia.org/…', 'session_id': '…'})
  ← tool_result [OK]: "Fetched and ingested 14821 chars from https://…"
...
────────────────────────────────────────────────────────────
╭──────────────────── Research Report ──────────────────╮
│ ## Summary                                            │
│ Python is a high-level programming language…          │
│                                                       │
│ ## Key Facts                                          │
│ - Created by Guido van Rossum in 1991…                │
│ …                                                     │
╰───────────────────────────────────────────────────────╯

Report saved to: /tmp/research/python_history.md

Steps: 8  |  Input tokens: 3421  |  Output tokens: 892  |  Stopped by: end_turn
```

## Architecture

```
main.py  ──►  create_research_agent()
                 ├── GroqProvider       (llama-3.3-70b-versatile via Groq API)
                 ├── AgentConfig        (max_iterations=20, verbose=True)
                 ├── ToolRegistry       [http_request, fetch_and_ingest,
                 │                       ingest_document, write_file,
                 │                       read_file, get_datetime]
                 ├── RAGMemory          (ChromaDB collection: "research-agent")
                 └── SessionManager     (FileCheckpointStore: .agentsdk/checkpoints/)
```

### Custom tool: `fetch_and_ingest`

```python
@tool
async def fetch_and_ingest(url: str, session_id: str) -> str:
    """Fetch a web page and ingest its content into vector memory."""
```

Strips `<script>`, `<style>`, and all other HTML tags, normalises whitespace, chunks the text into 500-character overlapping windows, and stores each chunk in the vector store for semantic retrieval during the same session.
