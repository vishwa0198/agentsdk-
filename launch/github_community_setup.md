# GitHub community setup

Run these commands from the repo root to create all community files:

```bash
mkdir -p .github/ISSUE_TEMPLATE
```

---

## .github/ISSUE_TEMPLATE/bug_report.md

```markdown
---
name: Bug report
about: Something is broken
labels: bug
---

**What happened:**

**Expected behaviour:**

**Steps to reproduce:**
\`\`\`python
# Minimal code to reproduce
\`\`\`

**Environment:**
- agentsdk-py version:
- Python version:
- OS:

**Error output:**
\`\`\`
paste traceback here
\`\`\`
```

---

## .github/ISSUE_TEMPLATE/feature_request.md

```markdown
---
name: Feature request
about: New tool, provider, or SDK feature
labels: enhancement
---

**What problem does this solve?**

**Proposed API (show how it would be used):**
\`\`\`python
# How you'd want to write it
\`\`\`

**Alternatives considered:**
```

---

## .github/PULL_REQUEST_TEMPLATE.md

```markdown
**What does this PR do?**

**How to test it:**
\`\`\`bash
# Commands to verify
\`\`\`

**Checklist**
- [ ] Tests added or updated
- [ ] `pytest tests/test_smoke.py` passes
- [ ] Docstrings updated if public API changed
- [ ] CHANGELOG.md entry added
```

---

## CONTRIBUTING.md

```markdown
# Contributing to agentsdk

## Setup

\`\`\`bash
git clone https://github.com/vishwa0198/agentsdk
cd agentsdk
pip install -e ".[dev]"
pytest tests/test_smoke.py  # should be 7/7
\`\`\`

## Where to contribute

- **New tools** → `agentsdk/tools/builtin.py` + test in `tests/test_smoke.py`
- **New LLM providers** → implement `LLMProvider` protocol in `agentsdk/llm.py`
- **Bug fixes** → open an issue first if non-trivial

## Code style

- Type hints everywhere
- Google-style docstrings on all public classes
- `async def` for anything that does I/O
- Pydantic v2 for all data models

## Running tests

\`\`\`bash
pytest tests/test_smoke.py          # no API key needed
pytest tests/test_integration.py    # needs GROQ_API_KEY
\`\`\`
```

---

## SECURITY.md

```markdown
# Security

## Reporting a vulnerability

Email: your-email@example.com

Please do not open a public GitHub issue for security vulnerabilities.
We will respond within 48 hours and aim to patch critical issues within 7 days.

## Known limitations

- `run_python` without Docker (`AGENTSDK_UNSAFE_PYTHON=1`) executes code
  directly — for development only, never expose to untrusted input
- `.agentsdk/users.json` stores bcrypt hashes — keep this file out of
  version control (it is in `.gitignore` by default)
- `GROQ_API_KEY` and `SECRET_KEY` must never be committed — always use `.env`
```

---

## GitHub repo settings checklist

### Enable in Settings → General
- [x] Discussions tab (Settings → General → Features → Discussions)
- [x] Issues
- [x] Projects (optional)

### Enable in Settings → Pages
- Source: `gh-pages` branch (docs auto-deploy via GitHub Actions)

### Enable in Settings → Branches
- Add protection rule for `main`:
  - Require pull request reviews before merging
  - Require status checks to pass (pytest)
  - Do not allow force pushes

### Community profile (Insights → Community)
Complete the checklist:
- [x] Description
- [x] README.md
- [x] Code of conduct (use standard GitHub template)
- [x] Contributing guidelines (CONTRIBUTING.md above)
- [x] License (MIT)
- [x] Security policy (SECURITY.md above)
- [x] Issue templates

---

## First pinned Discussion to create

**Title:** Welcome — introduce yourself and what you're building

**Body:**
> agentsdk is a new project and I'd love to know who's using it.
>
> Drop a comment: what are you building with it?
>
> Questions, feedback, and ideas all welcome here.
> I read every comment and respond to all of them.

Pin this discussion immediately after creating it.
