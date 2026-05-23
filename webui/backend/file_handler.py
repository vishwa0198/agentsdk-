"""webui/backend/file_handler.py

Multi-modal file parsing utilities.

Supported types
---------------
* PDF   — extract text via pypdf (optional; install with ``pip install pypdf``)
* CSV   — parse + format as a markdown table
* Image — base64-encode (.png/.jpg/.jpeg/.gif/.webp) for vision models
* Text  — UTF-8 read of .txt / .md / .json / .py / source files
* Other — raw bytes decoded as UTF-8 (best-effort)

The ``extract_text`` function is the single public entry-point; everything
else is internal.

Usage::

    from file_handler import extract_text, build_file_context

    info = extract_text("report.pdf", raw_bytes)
    # info == {"file_id": "a3b1c2d4", "filename": "report.pdf",
    #          "type": "pdf", "text": "...", "base64": None, "mime": "..."}
    context_block = build_file_context(info)
    full_message = context_block + "\\n\\n" + user_message
"""

from __future__ import annotations

import base64
import csv
import io
import mimetypes
import uuid
from pathlib import Path
from typing import Any

MAX_CSV_ROWS = 150          # rows shown in markdown table
MAX_TEXT_CHARS = 60_000     # character cap to avoid token overflow
MAX_FILE_BYTES = 20 * 1024 * 1024   # 20 MB hard limit

_TEXT_EXTENSIONS = {
    ".txt", ".md", ".rst", ".log", ".json", ".jsonl",
    ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
    ".sh", ".bash", ".zsh", ".sql", ".xml",
}

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_text(filename: str, content: bytes) -> dict[str, Any]:
    """Parse *content* bytes and return a structured info dict.

    Returns::

        {
            "file_id":  str,          # short random id
            "filename": str,
            "type":     str,          # "pdf" | "csv" | "image" | "text"
            "text":     str | None,   # extracted text (injected as context)
            "base64":   str | None,   # base64 image data (vision models)
            "mime":     str,
            "size":     int,          # raw byte count
        }
    """
    if len(content) > MAX_FILE_BYTES:
        return _error_result(filename, f"File too large ({len(content) // 1024} KB > 20 MB limit)")

    file_id = str(uuid.uuid4())[:8]
    suffix = Path(filename).suffix.lower()
    mime, _ = mimetypes.guess_type(filename)
    mime = mime or "application/octet-stream"

    if suffix == ".pdf":
        text = _parse_pdf(content)
        return _make(file_id, filename, "pdf", text, None, mime, len(content))

    if suffix == ".csv":
        text = _parse_csv(content)
        return _make(file_id, filename, "csv", text, None, mime, len(content))

    if suffix in _IMAGE_EXTENSIONS:
        b64 = base64.b64encode(content).decode()
        return _make(file_id, filename, "image", None, b64, mime, len(content))

    if suffix in _TEXT_EXTENSIONS:
        text = _decode_text(content)
        return _make(file_id, filename, "text", text, None, mime, len(content))

    # Binary fallback — try UTF-8, give up gracefully
    text = _decode_text(content)
    return _make(file_id, filename, "text", text, None, mime, len(content))


def build_file_context(file_info: dict[str, Any]) -> str:
    """Format *file_info* as a Markdown context block to prepend to the user message."""
    fname = file_info["filename"]
    ftype = file_info["type"]

    if ftype == "image":
        return f"[📎 Attached image: {fname}]"

    text = file_info.get("text") or ""
    if not text:
        return f"[📎 Attached {ftype.upper()}: {fname} — no text could be extracted]"

    lang = _lang_hint(fname)
    header = f"📎 **Attached {ftype.upper()}: {fname}**\n\n"
    if lang:
        return header + f"```{lang}\n{text}\n```"
    return header + text[:MAX_TEXT_CHARS]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make(
    file_id: str,
    filename: str,
    ftype: str,
    text: str | None,
    b64: str | None,
    mime: str,
    size: int,
) -> dict[str, Any]:
    return {
        "file_id": file_id,
        "filename": filename,
        "type": ftype,
        "text": text[:MAX_TEXT_CHARS] if text else text,
        "base64": b64,
        "mime": mime,
        "size": size,
    }


def _error_result(filename: str, msg: str) -> dict[str, Any]:
    return {
        "file_id": str(uuid.uuid4())[:8],
        "filename": filename,
        "type": "error",
        "text": f"[Error: {msg}]",
        "base64": None,
        "mime": "application/octet-stream",
        "size": 0,
    }


def _decode_text(content: bytes) -> str:
    try:
        return content.decode("utf-8", errors="replace")[:MAX_TEXT_CHARS]
    except Exception:
        return "[binary content — could not decode]"


def _lang_hint(filename: str) -> str:
    """Return a Markdown fenced-code language hint for source files."""
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".jsx": "jsx", ".tsx": "tsx", ".sh": "bash", ".sql": "sql",
        ".json": "json", ".yaml": "yaml", ".yml": "yaml",
        ".toml": "toml", ".html": "html", ".css": "css", ".xml": "xml",
        ".md": "markdown",
    }
    return ext_map.get(Path(filename).suffix.lower(), "")


def _parse_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import]
        reader = PdfReader(io.BytesIO(content))
        pages = []
        for i, page in enumerate(reader.pages):
            extracted = page.extract_text() or ""
            if extracted.strip():
                pages.append(f"[Page {i + 1}]\n{extracted}")
        return "\n\n".join(pages)[:MAX_TEXT_CHARS]
    except ImportError:
        return "[PDF support requires pypdf: pip install pypdf]"
    except Exception as exc:
        return f"[PDF parse error: {exc}]"


def _parse_csv(content: bytes) -> str:
    try:
        text = content.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = []
        for i, row in enumerate(reader):
            if i > MAX_CSV_ROWS:
                break
            rows.append(row)

        if not rows:
            return "(empty CSV file)"

        header = rows[0]
        col_count = len(header)
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(["---"] * col_count) + " |",
        ]
        for row in rows[1:]:
            padded = (row + [""] * col_count)[:col_count]
            # Escape pipe characters inside cells
            cells = [c.replace("|", "\\|") for c in padded]
            lines.append("| " + " | ".join(cells) + " |")

        total_rows = text.count("\n")
        note = (
            f"\n\n*(Showing {len(rows) - 1} of ~{total_rows} rows — file truncated)*"
            if total_rows > MAX_CSV_ROWS
            else ""
        )
        return "\n".join(lines) + note
    except Exception as exc:
        return f"[CSV parse error: {exc}]"
