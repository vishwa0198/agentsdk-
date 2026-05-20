# Coding Agent

An AI-powered Python coding agent built on **agentsdk**. Given a task description, it thinks through a solution, writes code, runs it in a sandbox, iterates until it works, then saves the final result.

## Features

- Iterative **write → test → fix** loop (up to 15 iterations)
- Persistent sessions — resume previous work with `--session`
- RAG memory (ChromaDB + sentence-transformers) for semantic context retrieval
- File checkpoint store for reliable JSON session persistence
- Rich terminal UI with spinner, panels, and trace summary

## Setup

```bash
# From the repository root
pip install -e ".[rag]"
pip install rich

# .env file with your Groq API key (already exists at repo root)
# GROQ_API_KEY=gsk_...
```

Allow the `run_python` tool to execute code locally (required without Docker):

```powershell
# PowerShell
$env:AGENTSDK_UNSAFE_PYTHON = "1"
```

```bash
# bash / zsh
export AGENTSDK_UNSAFE_PYTHON=1
```

## Usage

```bash
# Run from the projects/coding_agent/ directory
cd projects/coding_agent

# One-shot task
python main.py "Write a function that finds all prime numbers up to N using the Sieve of Eratosthenes"

# Interactive prompt (no argument)
python main.py

# Resume a named session
python main.py --session my-session "Add unit tests to the previous solution"
```

## Output

```
╭────────────────────────────────────────────────────╮
│     Coding Agent — powered by agentsdk             │
╰────────────────────────────────────────────────────╯
Task: Write a Sieve of Eratosthenes up to N
Session: coding-a3f7b2c1

[CodingAgent] iter=1 stop=tool_use thought="I'll write the sieve..."
  → tool_call: run_python(...)
  ← tool_result [OK]: "[2, 3, 5, 7, 11, ...]"
...
────────────────────────────────────────────────────────
╭────────────────── Solution ────────────────────────╮
│ Here is the Sieve of Eratosthenes implementation…  │
╰────────────────────────────────────────────────────╯

Steps: 3  |  Input tokens: 842  |  Output tokens: 431  |  Stopped by: end_turn
```

## Architecture

```
main.py  ──►  create_coding_agent()
                 ├── GroqProvider       (llama-3.3-70b-versatile via Groq API)
                 ├── AgentConfig        (max_iterations=15, verbose=True)
                 ├── ToolRegistry       [run_python, write_file, read_file]
                 ├── RAGMemory          (ChromaDB collection: "coding-agent")
                 └── SessionManager     (FileCheckpointStore: .agentsdk/checkpoints/)
```
