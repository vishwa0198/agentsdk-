"""agentsdk/tools/builtin.py

Ready-made tool bundle for common agent capabilities.

Quick start::

    from agentsdk.tools.builtin import DEFAULT_TOOLS
    agent = Agent(config=cfg, llm=llm, registry=DEFAULT_TOOLS)

All tools are safe to register together; individual tools can also be
imported and registered selectively.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import aiofiles
import httpx

from agentsdk.messages import HumanMessage
from agentsdk.tools.base import tool
from agentsdk.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# 1. http_request
# ---------------------------------------------------------------------------


@tool
async def http_request(url: str, method: str, body: str) -> str:
    """Make an HTTP GET or POST request and return the response body (max 3000 chars).

    method must be GET or POST. For POST, body is sent as raw JSON string.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if method.upper() == "POST":
                response = await client.post(
                    url,
                    content=body,
                    headers={"Content-Type": "application/json"},
                )
            else:
                response = await client.get(url)

            response.raise_for_status()
            return response.text[:3000]

    except httpx.HTTPStatusError as exc:
        return f"Error: {exc.response.status_code} {exc.response.reason_phrase}"
    except httpx.RequestError as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# 2. read_file
# ---------------------------------------------------------------------------


@tool
async def read_file(path: str) -> str:
    """Read a file from the local filesystem and return its text contents (max 5000 chars)."""
    if ".." in path:
        return "Error: path traversal not allowed"
    try:
        async with aiofiles.open(path, mode="r", encoding="utf-8") as f:
            content = await f.read()
        return content[:5000]
    except FileNotFoundError:
        return f"Error: file not found: {path}"
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# 3. write_file
# ---------------------------------------------------------------------------


@tool
async def write_file(path: str, content: str) -> str:
    """Write text content to a file, creating any missing parent directories."""
    if ".." in path:
        return "Error: path traversal not allowed"
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(target, mode="w", encoding="utf-8") as f:
            await f.write(content)
        return f"Written {len(content)} bytes to {path}"
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# 4. run_python
# ---------------------------------------------------------------------------


@tool
async def run_python(code: str) -> str:
    """Execute Python code safely in an isolated Docker container.

    Set AGENTSDK_UNSAFE_PYTHON=1 to fall back to a local subprocess (dev only).
    """
    # Production safe: no network, read-only fs, memory capped
    if os.environ.get("AGENTSDK_UNSAFE_PYTHON"):
        # ── Unsafe local fallback (dev without Docker) ─────────────────────
        # Uses run_in_executor so it works on any event loop (including
        # Windows SelectorEventLoop which rejects create_subprocess_exec).
        def _run_sync() -> str:
            try:
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return result.stdout.decode(errors="replace").strip()
                return f"Error: {result.stderr.decode(errors='replace').strip()}"
            except subprocess.TimeoutExpired:
                return "Error: timeout after 10s"
            except Exception as exc:  # noqa: BLE001
                return f"Error: {exc}"

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_sync)

    # ── Docker sandbox (production) ─────────────────────────────────────────
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        proc = await asyncio.create_subprocess_exec(
            "docker", "run", "--rm",
            "--network", "none",
            "--memory", "128m",
            "--cpus", "0.5",
            "--read-only",
            "--tmpfs", "/tmp:size=64m",
            "-v", f"{tmp_path}:/code/solution.py:ro",
            "python:3.12-slim",
            "python", "/code/solution.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return "Error: timeout after 15s"

        if proc.returncode == 0:
            return stdout.decode(errors="replace").strip()
        return f"Error: {stderr.decode(errors='replace')[:500]}"

    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 5. get_datetime
# ---------------------------------------------------------------------------


@tool
async def get_datetime() -> str:
    """Return the current UTC date and time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 6. ingest_document — RAG ingestion tool
# ---------------------------------------------------------------------------

# Module-level store; set via set_default_store() before using the tool.
_default_store: "VectorMemoryStore | None" = None  # type: ignore[name-defined]  # noqa: F821


def set_default_store(store: "VectorMemoryStore") -> None:  # type: ignore[name-defined]  # noqa: F821
    """Configure the :class:`~agentsdk.memory.VectorMemoryStore` used by
    :func:`ingest_document`.

    Call this once at application start-up before registering
    ``ingest_document`` in an agent.

    Args:
        store: A configured :class:`~agentsdk.memory.VectorMemoryStore` instance.
    """
    global _default_store
    _default_store = store


@tool
async def ingest_document(path: str, session_id: str) -> str:
    """Ingest a text or PDF file into vector memory for semantic retrieval.

    Reads the file at *path*, splits it into overlapping 500-character chunks,
    embeds each chunk, and stores them in the configured vector store under
    *session_id*.

    Supports plain-text files (any extension) and PDF files (``.pdf``).
    For PDF support ``pypdf`` must be installed (``pip install pypdf``).

    Args:
        path: Absolute or relative path to the file to ingest.
        session_id: Session identifier used to namespace the stored chunks.

    Returns:
        A human-readable summary such as ``"Ingested 12 chunks from report.pdf"``,
        or an error string if the store is not configured or the file cannot
        be read.
    """
    if _default_store is None:
        return "Error: no vector store configured. Call set_default_store() first."

    p = Path(path)

    # --- Read content ---
    if p.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore[import]
        except ImportError:
            return (
                "Error: pypdf not installed. "
                "Install it with: pip install pypdf"
            )
        try:
            reader = PdfReader(str(p))
            text = "\n".join(
                page.extract_text() or "" for page in reader.pages
            )
        except Exception as exc:  # noqa: BLE001
            return f"Error reading PDF: {exc}"
    else:
        try:
            async with aiofiles.open(str(p), encoding="utf-8", errors="replace") as f:
                text = await f.read()
        except OSError as exc:
            return f"Error reading file: {exc}"

    if not text.strip():
        return f"Error: no text extracted from {path}"

    # --- Chunk (500 chars, 50-char overlap) ---
    chunk_size, overlap = 500, 50
    step = chunk_size - overlap
    chunks = [
        text[i: i + chunk_size]
        for i in range(0, len(text), step)
        if text[i: i + chunk_size].strip()
    ]

    # --- Store each chunk ---
    for idx, chunk in enumerate(chunks):
        msg = HumanMessage(
            content=chunk,
            metadata={"source": str(p), "chunk": idx},
        )
        await _default_store.add(session_id, msg)

    return f"Ingested {len(chunks)} chunks from {path}"


# ---------------------------------------------------------------------------
# 7. GitHub tools
# ---------------------------------------------------------------------------

_GITHUB_API = "https://api.github.com"


def _github_headers() -> dict[str, str]:
    token = os.environ.get("GITHUB_TOKEN", "")
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@tool
async def github_get_repo(owner: str, repo: str) -> str:
    """Get basic info about a GitHub repository: description, stars, forks, open issues, default branch."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{owner}/{repo}",
                headers=_github_headers(),
            )
        except httpx.RequestError as exc:
            return f"Error: {exc}"

    if resp.status_code == 404:
        return "Error: repo not found"
    if resp.status_code == 401:
        return "Error: invalid or missing GITHUB_TOKEN"
    if not resp.is_success:
        return f"Error: {resp.status_code} from GitHub API"

    d = resp.json()
    return (
        f"{owner}/{repo} — {d.get('description') or 'No description'}\n"
        f"Stars: {d.get('stargazers_count', 0)} | "
        f"Forks: {d.get('forks_count', 0)} | "
        f"Open issues: {d.get('open_issues_count', 0)}\n"
        f"Default branch: {d.get('default_branch', 'main')}"
    )


@tool
async def github_list_issues(owner: str, repo: str, state: str) -> str:
    """List open or closed issues for a GitHub repo. state must be 'open' or 'closed'."""
    if state not in ("open", "closed"):
        return "Error: state must be 'open' or 'closed'"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{owner}/{repo}/issues",
                params={"state": state, "per_page": 10},
                headers=_github_headers(),
            )
        except httpx.RequestError as exc:
            return f"Error: {exc}"

    if resp.status_code == 404:
        return "Error: repo not found"
    if not resp.is_success:
        return f"Error: {resp.status_code} from GitHub API"

    issues = resp.json()
    if not issues:
        return f"No {state} issues found"

    lines = []
    for issue in issues:
        user = issue.get("user", {}).get("login", "unknown")
        lines.append(
            f"#{issue['number']} [{issue['state']}] {issue['title']} — {user}\n"
            f"  {issue['html_url']}"
        )
    return "\n".join(lines)


@tool
async def github_create_issue(owner: str, repo: str, title: str, body: str) -> str:
    """Create a new issue in a GitHub repository."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return "Error: GITHUB_TOKEN required"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{_GITHUB_API}/repos/{owner}/{repo}/issues",
                json={"title": title, "body": body},
                headers=_github_headers(),
            )
        except httpx.RequestError as exc:
            return f"Error: {exc}"

    if resp.status_code == 401:
        return "Error: invalid GITHUB_TOKEN"
    if resp.status_code == 404:
        return "Error: repo not found"
    if not resp.is_success:
        return f"Error: {resp.status_code} from GitHub API"

    d = resp.json()
    return f"Created issue #{d['number']}: {d['html_url']}"


@tool
async def github_get_file(owner: str, repo: str, path: str) -> str:
    """Get the contents of a file from a GitHub repository."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
                headers=_github_headers(),
            )
        except httpx.RequestError as exc:
            return f"Error: {exc}"

    if resp.status_code == 404:
        return f"Error: file not found: {path}"
    if not resp.is_success:
        return f"Error: {resp.status_code} from GitHub API"

    d = resp.json()
    encoded = d.get("content", "")
    # GitHub base64-encodes content with newlines; strip them before decoding.
    content = base64.b64decode(encoded.replace("\n", "")).decode(errors="replace")
    return content[:4000]


# ---------------------------------------------------------------------------
# 8. Web scraping tools
# ---------------------------------------------------------------------------

_SCRAPER_UA = "Mozilla/5.0 (compatible; agentsdk-scraper/1.0)"


@tool
async def scrape_webpage(url: str, selector: str) -> str:
    """Fetch a webpage and extract text content. selector is a CSS selector (e.g. 'article', 'main', 'body') — use 'body' to get all text."""
    try:
        from bs4 import BeautifulSoup  # type: ignore[import]
    except ImportError:
        return "Error: beautifulsoup4 not installed. Run: pip install beautifulsoup4"

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": _SCRAPER_UA},
        ) as client:
            resp = await client.get(url)
    except httpx.TimeoutException:
        return f"Error: timeout fetching {url}"
    except httpx.RequestError as exc:
        return f"Error: {exc}"

    if not resp.is_success:
        return f"Error: {resp.status_code} fetching {url}"

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove noise tags.
    for tag in soup.find_all(["script", "style", "nav", "footer"]):
        tag.decompose()

    # Try requested selector, fall back to body.
    elements = soup.select(selector)
    root = elements[0] if elements else soup.body
    if root is None:
        root = soup

    text = root.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:5000]


@tool
async def extract_links(url: str) -> str:
    """Fetch a webpage and return all hyperlinks found on the page."""
    try:
        from bs4 import BeautifulSoup  # type: ignore[import]
    except ImportError:
        return "Error: beautifulsoup4 not installed. Run: pip install beautifulsoup4"

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": _SCRAPER_UA},
        ) as client:
            resp = await client.get(url)
    except httpx.TimeoutException:
        return f"Error: timeout fetching {url}"
    except httpx.RequestError as exc:
        return f"Error: {exc}"

    if not resp.is_success:
        return f"Error: {resp.status_code} fetching {url}"

    soup = BeautifulSoup(resp.text, "html.parser")
    seen: set[str] = set()
    lines: list[str] = []

    for a in soup.find_all("a", href=True):
        href: str = urljoin(url, a["href"])
        parsed = urlparse(href)
        if parsed.scheme not in ("http", "https"):
            continue
        # Normalise: drop fragment.
        href = parsed._replace(fragment="").geturl()
        if href in seen:
            continue
        seen.add(href)
        text = (a.get_text(strip=True) or "[no text]")[:50]
        lines.append(f"{text} — {href}")
        if len(lines) >= 30:
            break

    return "\n".join(lines) if lines else "No links found"


# ---------------------------------------------------------------------------
# 9. SQL tools
# ---------------------------------------------------------------------------

_DESTRUCTIVE_RE = re.compile(
    r"^\s*(DROP|TRUNCATE|ALTER)\b"
    r"|^\s*DELETE\s+FROM\b(?!.*\bWHERE\b)",
    re.IGNORECASE | re.DOTALL,
)


def _format_table(columns: list[str], rows: list[tuple]) -> str:  # type: ignore[type-arg]
    """Render a markdown table from column names and row data."""
    if not rows:
        return "No results"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    data_rows = [
        "| " + " | ".join(str(v)[:30] for v in row) + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *data_rows])


@tool
async def sql_query(database_url: str, query: str) -> str:
    """Run a SQL query against a SQLite or PostgreSQL database. Returns results as a formatted table."""
    # Safety: reject destructive statements.
    if _DESTRUCTIVE_RE.match(query):
        return (
            "Error: destructive statements not allowed. "
            "Use SELECT, INSERT, or UPDATE with WHERE."
        )

    if database_url.startswith("sqlite:///"):
        path = database_url[len("sqlite:///"):]
        try:
            import aiosqlite  # type: ignore[import]
        except ImportError:
            return "Error: aiosqlite not installed. Run: pip install aiosqlite"
        try:
            async with aiosqlite.connect(path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(query) as cursor:
                    rows = await cursor.fetchmany(50)
                    if not rows:
                        return "No results"
                    columns = list(rows[0].keys())
                    return _format_table(columns, [tuple(r) for r in rows])
        except Exception as exc:  # noqa: BLE001
            return f"Error: {exc}"

    elif database_url.startswith(("postgresql://", "postgres://")):
        try:
            import asyncpg  # type: ignore[import]
        except ImportError:
            return "Error: asyncpg not installed. Run: pip install asyncpg"
        try:
            conn = await asyncpg.connect(database_url)
            try:
                rows = await conn.fetch(query)
            finally:
                await conn.close()
            if not rows:
                return "No results"
            columns = list(rows[0].keys())
            return _format_table(columns, [tuple(r) for r in rows[:50]])
        except Exception as exc:  # noqa: BLE001
            return f"Error: {exc}"

    else:
        return (
            "Error: unsupported database URL. "
            "Use sqlite:///path or postgresql://..."
        )


@tool
async def sql_schema(database_url: str) -> str:
    """Get the schema (tables and columns) of a SQLite or PostgreSQL database."""
    if database_url.startswith("sqlite:///"):
        path = database_url[len("sqlite:///"):]
        try:
            import aiosqlite  # type: ignore[import]
        except ImportError:
            return "Error: aiosqlite not installed. Run: pip install aiosqlite"
        try:
            async with aiosqlite.connect(path) as db:
                async with db.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
                ) as cursor:
                    tables = await cursor.fetchall()
            if not tables:
                return "No tables found"
            lines = []
            for name, sql in tables:
                lines.append(f"## {name}\n{sql or ''}")
            return "\n\n".join(lines)[:3000]
        except Exception as exc:  # noqa: BLE001
            return f"Error: {exc}"

    elif database_url.startswith(("postgresql://", "postgres://")):
        try:
            import asyncpg  # type: ignore[import]
        except ImportError:
            return "Error: asyncpg not installed. Run: pip install asyncpg"
        try:
            conn = await asyncpg.connect(database_url)
            try:
                rows = await conn.fetch(
                    "SELECT table_name, column_name, data_type "
                    "FROM information_schema.columns "
                    "WHERE table_schema='public' "
                    "ORDER BY table_name, ordinal_position"
                )
            finally:
                await conn.close()
            if not rows:
                return "No tables found"
            # Group by table.
            schema: dict[str, list[str]] = {}
            for row in rows:
                schema.setdefault(row["table_name"], []).append(
                    f"  {row['column_name']} ({row['data_type']})"
                )
            lines = []
            for table, cols in schema.items():
                lines.append(f"## {table}\n" + "\n".join(cols))
            return "\n\n".join(lines)[:3000]
        except Exception as exc:  # noqa: BLE001
            return f"Error: {exc}"

    else:
        return (
            "Error: unsupported database URL. "
            "Use sqlite:///path or postgresql://..."
        )


# ---------------------------------------------------------------------------
# 10. Browser automation tools (requires: pip install playwright && playwright install chromium)
# ---------------------------------------------------------------------------


@tool
async def browser_open(url: str) -> str:
    """Open a URL in a headless browser and return the page title and main text content."""
    try:
        from playwright.async_api import async_playwright  # type: ignore[import]
    except ImportError:
        return "Error: playwright not installed. Run: pip install playwright && playwright install chromium"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, timeout=30000)
            except Exception as exc:
                await browser.close()
                if "timeout" in str(exc).lower() or "Timeout" in type(exc).__name__:
                    return f"Error: page load timeout for {url}"
                return f"Error: {exc}"
            title = await page.title()
            text = await page.inner_text("body")
            text = re.sub(r"\s{3,}", " ", text).strip()
            await browser.close()
            return f"Title: {title}\n\nContent:\n{text[:3000]}"
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"


@tool
async def browser_click(url: str, selector: str) -> str:
    """Open a URL, click an element by CSS selector, return resulting page content."""
    try:
        from playwright.async_api import async_playwright  # type: ignore[import]
    except ImportError:
        return "Error: playwright not installed. Run: pip install playwright && playwright install chromium"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=30000)
            element = await page.query_selector(selector)
            if element is None:
                await browser.close()
                return f"Error: selector '{selector}' not found"
            try:
                async with page.expect_navigation(timeout=10000):
                    await element.click()
            except Exception:
                await page.wait_for_timeout(1000)
            title = await page.title()
            text = await page.inner_text("body")
            text = re.sub(r"\s{3,}", " ", text).strip()
            await browser.close()
            return f"Title: {title}\n\nContent:\n{text[:2000]}"
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"


@tool
async def browser_screenshot(url: str, save_path: str) -> str:
    """Take a full-page screenshot of a URL and save it to save_path."""
    if ".." in save_path:
        return "Error: path traversal not allowed"
    try:
        from playwright.async_api import async_playwright  # type: ignore[import]
    except ImportError:
        return "Error: playwright not installed. Run: pip install playwright && playwright install chromium"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=30000)
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=save_path, full_page=True)
            await browser.close()
            return f"Screenshot saved to {save_path}"
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"


@tool
async def browser_fill_form(url: str, fields: str, submit_selector: str) -> str:
    """Fill a web form and submit it. fields is a JSON string mapping CSS selectors to values."""
    try:
        from playwright.async_api import async_playwright  # type: ignore[import]
    except ImportError:
        return "Error: playwright not installed. Run: pip install playwright && playwright install chromium"
    try:
        field_map: dict = json.loads(fields)
    except json.JSONDecodeError as exc:
        return f"Error: invalid JSON in fields: {exc}"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=30000)
            for sel, value in field_map.items():
                await page.fill(sel, str(value))
            try:
                async with page.expect_navigation(timeout=10000):
                    await page.click(submit_selector)
            except Exception:
                await page.wait_for_timeout(1000)
            new_url = page.url
            await browser.close()
            return f"Form submitted. Landed on: {new_url}"
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# 11. Email tools (send: pip install aiosmtplib; read: stdlib imaplib)
# ---------------------------------------------------------------------------


@tool
async def send_email(to: str, subject: str, body: str) -> str:
    """Send an email using SMTP. Uses SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS from .env"""
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    if not all([smtp_host, smtp_user, smtp_pass]):
        return (
            "Error: set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS in .env "
            "— use Mailtrap free tier at mailtrap.io"
        )
    try:
        import aiosmtplib  # type: ignore[import]
    except ImportError:
        return "Error: aiosmtplib not installed. Run: pip install aiosmtplib"
    try:
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user,
            password=smtp_pass,
            start_tls=True,
        )
        return f"Email sent to {to} — subject: '{subject}'"
    except Exception as exc:  # noqa: BLE001
        return f"Error sending email: {exc}"


@tool
async def read_emails(max_count: int) -> str:
    """Read latest emails from IMAP inbox. Uses IMAP_HOST, IMAP_USER, IMAP_PASS from .env"""
    imap_host = os.environ.get("IMAP_HOST")
    imap_user = os.environ.get("IMAP_USER")
    imap_pass = os.environ.get("IMAP_PASS")
    if not all([imap_host, imap_user, imap_pass]):
        return "Error: set IMAP_HOST, IMAP_USER, IMAP_PASS in .env"
    count = min(max_count, 10)

    def _fetch() -> str:
        import email as _email_stdlib
        import imaplib

        try:
            with imaplib.IMAP4_SSL(imap_host) as mail:
                mail.login(imap_user, imap_pass)
                mail.select("INBOX")
                _, data = mail.search(None, "ALL")
                ids = data[0].split()
                selected = ids[-count:] if len(ids) >= count else ids
                lines: list[str] = []
                for i, uid in enumerate(reversed(selected), start=1):
                    _, msg_data = mail.fetch(uid, "(RFC822)")
                    raw = msg_data[0][1]
                    msg = _email_stdlib.message_from_bytes(raw)
                    from_addr = msg.get("From", "Unknown")
                    subj = msg.get("Subject", "(No Subject)")
                    date = msg.get("Date", "Unknown")
                    preview = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                preview = (
                                    part.get_payload(decode=True)
                                    .decode(errors="replace")[:300]
                                )
                                break
                    else:
                        preview = msg.get_payload(decode=True).decode(errors="replace")[:300]
                    lines.append(
                        f"[{i}] From: {from_addr}\n"
                        f"    Subject: {subj}\n"
                        f"    Date: {date}\n"
                        f"    Preview: {preview}"
                    )
                return "\n\n".join(lines) if lines else "No emails found"
        except Exception as exc:  # noqa: BLE001
            return f"Error reading emails: {exc}"

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch)


# ---------------------------------------------------------------------------
# 12. Discord tools (REST API via httpx — no extra dependency needed)
# ---------------------------------------------------------------------------

_DISCORD_API = "https://discord.com/api/v10"


@tool
async def discord_send_message(channel_id: str, message: str) -> str:
    """Send a message to a Discord channel using DISCORD_BOT_TOKEN from .env"""
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        return (
            "Error: set DISCORD_BOT_TOKEN in .env "
            "— create a free bot at discord.com/developers"
        )
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_DISCORD_API}/channels/{channel_id}/messages",
                json={"content": message},
                headers=headers,
            )
        if resp.status_code == 403:
            return f"Error: bot lacks permission to post in channel {channel_id}"
        if resp.status_code == 404:
            return f"Error: channel {channel_id} not found"
        resp.raise_for_status()
        return f"Message sent to channel {channel_id}"
    except httpx.HTTPStatusError as exc:
        return f"Error: {exc.response.status_code}"
    except httpx.RequestError as exc:
        return f"Error: {exc}"


@tool
async def discord_read_messages(channel_id: str, count: int) -> str:
    """Read recent messages from a Discord channel."""
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        return (
            "Error: set DISCORD_BOT_TOKEN in .env "
            "— create a free bot at discord.com/developers"
        )
    headers = {"Authorization": f"Bot {token}"}
    limit = min(count, 50)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_DISCORD_API}/channels/{channel_id}/messages",
                params={"limit": limit},
                headers=headers,
            )
        if resp.status_code == 403:
            return f"Error: bot lacks permission to read channel {channel_id}"
        if resp.status_code == 404:
            return f"Error: channel {channel_id} not found"
        resp.raise_for_status()
        msgs = resp.json()
        if not msgs:
            return "No messages found"
        lines = [
            f"[{m.get('timestamp', '')[:19]}] "
            f"{m.get('author', {}).get('username', 'unknown')}: "
            f"{m.get('content', '')}"
            for m in msgs
        ]
        return "\n".join(lines)
    except httpx.RequestError as exc:
        return f"Error: {exc}"


@tool
async def discord_list_guild_channels(guild_id: str) -> str:
    """List all text channels in a Discord server (guild)."""
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        return (
            "Error: set DISCORD_BOT_TOKEN in .env "
            "— create a free bot at discord.com/developers"
        )
    headers = {"Authorization": f"Bot {token}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_DISCORD_API}/guilds/{guild_id}/channels",
                headers=headers,
            )
        if resp.status_code == 403:
            return f"Error: bot lacks permission to view guild {guild_id}"
        if resp.status_code == 404:
            return f"Error: guild {guild_id} not found"
        resp.raise_for_status()
        channels = [c for c in resp.json() if c.get("type") == 0][:20]
        if not channels:
            return "No text channels found"
        return "\n".join(f"#{c['name']} (ID: {c['id']})" for c in channels)
    except httpx.RequestError as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# 13. Local calendar tools (no OAuth — stored in .agentsdk/calendar.json)
# ---------------------------------------------------------------------------

_CALENDAR_FILE = Path(".agentsdk") / "calendar.json"


def _load_calendar() -> list:
    if not _CALENDAR_FILE.exists():
        return []
    try:
        return json.loads(_CALENDAR_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def _save_calendar(events: list) -> None:
    _CALENDAR_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CALENDAR_FILE.write_text(
        json.dumps(events, indent=2, default=str), encoding="utf-8"
    )


@tool
async def calendar_list_events(days_ahead: int) -> str:
    """List calendar events for the next N days from local calendar store."""
    loop = asyncio.get_event_loop()
    events = await loop.run_in_executor(None, _load_calendar)
    now = datetime.now()
    cutoff = now + timedelta(days=days_ahead)
    upcoming = []
    for ev in events:
        try:
            start = datetime.fromisoformat(ev["start_time"])
            if now <= start <= cutoff:
                upcoming.append(ev)
        except (KeyError, ValueError):
            continue
    upcoming.sort(key=lambda e: e["start_time"])
    if not upcoming:
        return f"No events in the next {days_ahead} days"
    lines = [
        f"{ev['start_time']} — {ev['title']}"
        + (f" ({ev['description']})" if ev.get("description") else "")
        for ev in upcoming
    ]
    return "\n".join(lines)


@tool
async def calendar_create_event(
    title: str, start_time: str, end_time: str, description: str
) -> str:
    """Create a local calendar event. Times must be ISO format: 2026-05-21T14:00:00"""
    try:
        datetime.fromisoformat(start_time)
        datetime.fromisoformat(end_time)
    except ValueError:
        return (
            "Error: start_time and end_time must be valid ISO datetime strings "
            "(e.g. 2026-05-21T14:00:00)"
        )
    event_id = str(uuid4())[:8]
    event = {
        "event_id": event_id,
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "description": description,
        "created_at": datetime.now().isoformat(),
    }
    loop = asyncio.get_event_loop()
    events = await loop.run_in_executor(None, _load_calendar)
    events.append(event)
    await loop.run_in_executor(None, _save_calendar, events)
    return f"Event created: '{title}' on {start_time} — ID: {event_id}"


@tool
async def calendar_delete_event(event_id: str) -> str:
    """Delete a local calendar event by its event ID."""
    loop = asyncio.get_event_loop()
    events = await loop.run_in_executor(None, _load_calendar)
    new_events = [e for e in events if e.get("event_id") != event_id]
    if len(new_events) == len(events):
        return f"Error: event {event_id} not found"
    await loop.run_in_executor(None, _save_calendar, new_events)
    return f"Event {event_id} deleted"


@tool
async def calendar_search_events(query: str) -> str:
    """Search local calendar events by title or description keyword."""
    loop = asyncio.get_event_loop()
    events = await loop.run_in_executor(None, _load_calendar)
    q = query.lower()
    matches = [
        e for e in events
        if q in e.get("title", "").lower() or q in e.get("description", "").lower()
    ]
    if not matches:
        return f"No events found matching '{query}'"
    lines = [
        f"{ev['start_time']} — {ev['title']}"
        + (f" ({ev['description']})" if ev.get("description") else "")
        for ev in matches
    ]
    return "\n".join(lines)


DEFAULT_TOOLS = ToolRegistry()
DEFAULT_TOOLS.register_many(
    [
        http_request,
        read_file,
        write_file,
        run_python,
        get_datetime,
        ingest_document,
        # GitHub
        github_get_repo,
        github_list_issues,
        github_create_issue,
        github_get_file,
        # Web scraping
        scrape_webpage,
        extract_links,
        # SQL
        sql_query,
        sql_schema,
        # Browser automation
        browser_open,
        browser_click,
        browser_screenshot,
        browser_fill_form,
        # Email
        send_email,
        read_emails,
        # Discord
        discord_send_message,
        discord_read_messages,
        discord_list_guild_channels,
        # Calendar (local)
        calendar_list_events,
        calendar_create_event,
        calendar_delete_event,
        calendar_search_events,
    ]
)
