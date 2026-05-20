#!/usr/bin/env python
"""Coding Agent CLI — interactive interface for the CodingAgent.

Usage::

    python main.py "Write a Sieve of Eratosthenes up to N"
    python main.py --session my-session "Add unit tests to the previous solution"
    python main.py                          # interactive prompt
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid

# Ensure agent.py in this directory is importable regardless of cwd.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from agent import create_coding_agent

console = Console()


# ---------------------------------------------------------------------------
# Async core
# ---------------------------------------------------------------------------


async def _run(task: str, session_id: str) -> None:
    """Instantiate the agent, run it, and print results to the console."""
    agent = create_coding_agent()

    # ── Banner ────────────────────────────────────────────────────────────
    console.print(
        Panel(
            "[bold cyan]Coding Agent — powered by agentsdk[/bold cyan]",
            expand=False,
        )
    )
    console.print(f"[bold]Task:[/bold] {task}")
    console.print(f"[dim]Session:[/dim] [cyan]{session_id}[/cyan]\n")

    # ── Run with spinner ──────────────────────────────────────────────────
    # verbose=True on the agent already streams step output;
    # the spinner provides a visual indicator between printed steps.
    with console.status("[yellow]Thinking…[/yellow]", spinner="dots"):
        result = await agent.run(task, session_id=session_id)

    # ── Output panel ──────────────────────────────────────────────────────
    console.print(Rule())
    console.print(
        Panel(
            result.output,
            title="[bold green]Solution[/bold green]",
            expand=False,
        )
    )

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
        description="Coding Agent — write, test, and save Python code.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python main.py "Write a Sieve of Eratosthenes up to N"\n'
            '  python main.py --session my-session "Add unit tests"\n'
        ),
    )
    parser.add_argument("task", nargs="?", help="Coding task description.")
    parser.add_argument(
        "--session",
        default=None,
        metavar="ID",
        help="Resume or create a named session (default: random ID).",
    )
    args = parser.parse_args()

    task: str = args.task or console.input("[bold]Enter task:[/bold] ").strip()
    if not task:
        console.print("[red]No task provided. Exiting.[/red]")
        sys.exit(1)

    session_id: str = args.session or f"coding-{uuid.uuid4().hex[:8]}"

    asyncio.run(_run(task, session_id))


if __name__ == "__main__":
    main()
