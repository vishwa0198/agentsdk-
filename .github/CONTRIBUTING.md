# Contributing to agentsdk

Thanks for your interest in contributing! This guide explains how to get set up
and what to expect from the process.

## Quick start

```bash
git clone https://github.com/vishwa0198/agentsdk
cd agentsdk
pip install -e ".[dev,rag]"
```

Run the test suite before making any changes:

```bash
pytest tests/ -x -q
```

## Making a change

1. **Fork** the repo and create a feature branch from `main`.
2. Make your changes. Keep commits focused — one logical change per commit.
3. Add or update tests. PRs that drop test coverage will not be merged.
4. Run `pytest tests/ -x -q` and confirm everything passes.
5. Open a Pull Request against `main`. Fill in the PR template.

## What we accept

| ✅ Welcome | ❌ Please discuss first |
|---|---|
| Bug fixes with a failing test | Large refactors |
| New tool implementations | New top-level dependencies |
| Documentation improvements | Breaking API changes |
| New `projects/` cookbook examples | Changes to the release process |

For anything in the "discuss first" column, open a GitHub Discussion or Issue
before writing code — it saves everyone time.

## Code style

- Python: follow the style in the existing files (no strict linter enforced yet).
- Type annotations on all public functions.
- Docstrings on public classes and methods.
- No print statements in library code — use `logging`.

## Web UI changes

The `webui/` directory contains a FastAPI backend and a React frontend.

```bash
# Backend
cd webui/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd webui/frontend
npm install
npm run dev          # http://localhost:3000
```

Copy `webui/.env.example` → `webui/.env` and fill in `GROQ_API_KEY` and `SECRET_KEY`
before starting the backend.

## Commit message format

```
<type>: <short summary>

[optional body]
```

Types: `fix`, `feat`, `docs`, `test`, `refactor`, `chore`.

## Reporting bugs

Open a [GitHub Issue](https://github.com/vishwa0198/agentsdk/issues) with:
- Python version and OS
- Minimal reproduction script
- Full traceback
