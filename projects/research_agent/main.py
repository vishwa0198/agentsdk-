#!/usr/bin/env python
"""Research Agent CLI — interactive interface for the ResearchAgent.

Usage::

    python main.py "The history and impact of Python programming language"
    python main.py --session my-session "How does the Groq LPU architecture work"
    python main.py                          # interactive prompt
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

# Ensure agent.py in this directory is importable regardless of cwd.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from agent import create_research_agent

console = Console()

# Directory the agent saves reports into (matches SYSTEM_PROMPT).
_REPORT_DIR = Path("/tmp/research")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_latest_report(before_files: set[Path]) -> Path | None:
    """Return the newest .md file in _REPORT_DIR that wasn't there before the run."""
    if not _REPORT_DIR.exists():
        return None
    current = {p for p in _REPORT_DIR.glob("*.md")}
    new_files = current - before_files
    if not new_files:
        # Fall back to most-recently-modified file overall.
        all_md = sorted(_REPORT_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        return all_md[0] if all_md else None
    return max(new_files, key=lambda p: p.stat().st_mtime)


# ---------------------------------------------------------------------------
# Async core
# ---------------------------------------------------------------------------


async def _run(topic: str, session_id: str) -> None:
    """Instantiate the agent, run it, and print results to the console."""
    agent = create_research_agent()

    # ── Banner ────────────────────────────────────────────────────────────
    console.print(
        Panel(
            "[bold cyan]Research Agent — powered by agentsdk[/bold cyan]",
            expand=False,
        )
    )
    console.print(f"[bold]Topic:[/bold] {topic}")
    console.print(f"[dim]Session:[/dim] [cyan]{session_id}[/cyan]\n")
    console.print("[dim]Agent steps will appear below as they complete…[/dim]\n")

    # Snapshot existing reports before the run so we can identify new ones.
    before_files: set[Path] = set(_REPORT_DIR.glob("*.md")) if _REPORT_DIR.exists() else set()

    # ── Run — verbose=True streams each step automatically ────────────────
    result = await agent.run(topic, session_id=session_id)

    # ── Output panel ──────────────────────────────────────────────────────
    console.print(Rule())
    console.print(
        Panel(
            result.output,
            title="[bold green]Research Report[/bold green]",
            expand=False,
        )
    )

    # ── Saved report path ─────────────────────────────────────────────────
    latest = _find_latest_report(before_files)
    if latest:
        console.print(f"\n[bold green]Report saved to:[/bold green] {latest}")
        # Offer to print the report content if it differs from agent output.
        try:
            report_text = latest.read_text(encoding="utf-8")
            if report_text.strip() != result.output.strip():
                console.print(
                    Panel(
                        report_text,
                        title=f"[dim]{latest.name}[/dim]",
                        expand=False,
                    )
                )
        except OSError:
            pass
    else:
        console.print("\n[dim]No .md report found in /tmp/research/ — check agent output above.[/dim]")

    # ── Trace summary ─────────────────────────────────────────────────────
    console.print(
        f"\n[dim]Steps: {len(result.steps)}  |  "
        f"Input tokens: {result.total_input_tokens}  |  "
        f"Output tokens: {result.total_output_tokens}  |  "
        f"Stopped by: [bold]{result.stopped_by}[/bold][/dim]"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Research Agent — fetch, analyse, and report on any topic.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python main.py "The history and impact of Python programming language"\n'
            '  python main.py --session groq-research "How does the Groq LPU architecture work"\n'
        ),
    )
    parser.add_argument("topic", nargs="?", help="Research topic.")
    parser.add_argument(
        "--session",
        default=None,
        metavar="ID",
        help="Resume or create a named session (default: random ID).",
    )
    args = parser.parse_args()

    topic: str = args.topic or console.input("[bold]Enter research topic:[/bold] ").strip()
    if not topic:
        console.print("[red]No topic provided. Exiting.[/red]")
        sys.exit(1)

    session_id: str = args.session or f"research-{uuid.uuid4().hex[:8]}"

    asyncio.run(_run(topic, session_id))


if __name__ == "__main__":
    main()
