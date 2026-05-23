"""agentsdk/cli.py

scaffold-agent CLI — four commands:
  new           Create a new agent project with boilerplate
  run           Load an agent module and start an interactive REPL
  trace         Display message history from a checkpoint JSON file
  list-sessions List all saved sessions for a named agent
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

app = typer.Typer(
    name="scaffold-agent",
    help="agentsdk scaffolding and development CLI.",
    add_completion=False,
)
console = Console()


# ---------------------------------------------------------------------------
# Project scaffold templates
# ---------------------------------------------------------------------------

_AGENTS_MAIN = '''\
import asyncio
import os
import sys
from pathlib import Path

# Make the project root importable when run directly.
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from agentsdk import Agent, AgentConfig, GroqProvider, FileCheckpointStore, SessionManager

from tools.custom_tools import custom_tools_registry

load_dotenv()

_store = FileCheckpointStore(base_dir=".agentsdk/checkpoints")
_session_mgr = SessionManager(store=_store, agent_name="__NAME__")

agent = Agent(
    config=AgentConfig(
        name="__NAME__",
        system_prompt="You are a helpful assistant. Use the available tools when needed.",
        verbose=True,
    ),
    llm=GroqProvider(api_key=os.environ["GROQ_API_KEY"]),
    registry=custom_tools_registry,
    session_manager=_session_mgr,
)


async def main() -> None:
    result = await agent.run("Hello! What tools do you have available?")
    print(result.output)


if __name__ == "__main__":
    asyncio.run(main())
'''

_CUSTOM_TOOLS = '''\
from agentsdk import tool, ToolRegistry


@tool
async def greet(name: str) -> str:
    """Greet a person by name."""
    return f"Hello, {name}! Nice to meet you."


@tool
async def add(a: int, b: int) -> str:
    """Add two integers and return the result."""
    return str(a + b)


custom_tools_registry = ToolRegistry()
custom_tools_registry.register_many([greet, add])
'''

_MAIN_PY = '''\
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from agents.main import agent

console = Console()


async def main() -> None:
    agent_name = agent.config.name
    console.print(
        f"\\n[bold green]Welcome to {agent_name}![/] "
        "Type [bold]exit[/bold] to quit.\\n"
    )
    while True:
        try:
            user_input = Prompt.ask(f"[cyan]{agent_name}[/cyan]")
        except (KeyboardInterrupt, EOFError):
            console.print("\\n[yellow]Goodbye![/yellow]")
            break

        user_input = user_input.strip()
        if user_input.lower() in ("exit", "quit"):
            console.print("[yellow]Goodbye![/yellow]")
            break
        if not user_input:
            continue

        response = await agent.chat(user_input, session_id="main-session")
        console.print(Panel(response, title=agent_name, border_style="blue"))


if __name__ == "__main__":
    asyncio.run(main())
'''

_ENV_EXAMPLE = "GROQ_API_KEY=your_key_here\n"

_REQUIREMENTS = "agentsdk[otel]\npython-dotenv\n"

_README_TEMPLATE = '''\
# __NAME__

An AI agent built with [agentsdk](https://github.com/agentsdk/agentsdk).

## Setup

1. Copy `.env.example` to `.env` and add your Groq API key.
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the agent:
   ```
   python main.py
   ```

## Interactive CLI

```
scaffold-agent run agents/main.py
```
'''


def _write(path: Path, content: str, name: str) -> None:
    """Write *content* to *path*, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------


@app.command()
def new(name: str = typer.Argument(..., help="Project name (becomes the directory name)")) -> None:
    """Create a new agent project scaffold at ./<name>/."""
    root = Path(name)
    if root.exists():
        console.print(f"[red]Directory already exists:[/] {name}")
        raise typer.Exit(1)

    content = {
        root / "agents" / "__init__.py": "",
        root / "agents" / "main.py": _AGENTS_MAIN.replace("__NAME__", name),
        root / "tools" / "__init__.py": "",
        root / "tools" / "custom_tools.py": _CUSTOM_TOOLS,
        root / ".env.example": _ENV_EXAMPLE,
        root / "main.py": _MAIN_PY,
        root / "requirements.txt": _REQUIREMENTS,
        root / "README.md": _README_TEMPLATE.replace("__NAME__", name),
    }

    for path, text in content.items():
        _write(path, text, name)

    # Pretty tree
    tree = Tree(f"[bold green]{name}/[/bold green]")
    agents_branch = tree.add("[bold blue]agents/[/bold blue]")
    agents_branch.add("__init__.py")
    agents_branch.add("main.py")
    tools_branch = tree.add("[bold blue]tools/[/bold blue]")
    tools_branch.add("__init__.py")
    tools_branch.add("custom_tools.py")
    tree.add(".env.example")
    tree.add("main.py")
    tree.add("requirements.txt")
    tree.add("README.md")

    console.print()
    console.print(f"[bold green]✓[/bold green] Project created: [bold]{name}/[/bold]")
    console.print(tree)
    console.print(
        f"\nNext steps:\n"
        f"  1. [cyan]cd {name}[/cyan]\n"
        f"  2. Copy [cyan].env.example[/cyan] → [cyan].env[/cyan] and fill in your key\n"
        f"  3. [cyan]pip install -r requirements.txt[/cyan]\n"
        f"  4. [cyan]python main.py[/cyan]"
    )


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@app.command()
def run(
    agent_file: str = typer.Argument(..., help="Path to a Python file that defines a module-level 'agent' variable"),
) -> None:
    """Load an agent module and start an interactive REPL."""
    path = Path(agent_file).resolve()
    if not path.exists():
        console.print(f"[red]File not found:[/] {agent_file}")
        raise typer.Exit(1)

    # Add the file's directory to sys.path so relative imports work.
    file_dir = str(path.parent)
    if file_dir not in sys.path:
        sys.path.insert(0, file_dir)

    spec = importlib.util.spec_from_file_location("_agentsdk_run_module", path)
    if spec is None or spec.loader is None:
        console.print(f"[red]Cannot load module from:[/] {agent_file}")
        raise typer.Exit(1)

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        console.print(f"[red]Error loading module:[/] {exc}")
        raise typer.Exit(1)

    agent = getattr(module, "agent", None)
    if agent is None:
        console.print(
            f"[red]No module-level 'agent' variable found in[/] {agent_file}\n"
            "Define [cyan]agent = Agent(...)[/cyan] at the top level of the file."
        )
        raise typer.Exit(1)

    agent_name = getattr(getattr(agent, "config", None), "name", "Agent")
    console.print(
        f"\n[bold green]Loaded:[/bold green] [bold]{agent_name}[/bold]  "
        f"([dim]{agent_file}[/dim])\n"
        "Type [bold]exit[/bold] or press [bold]Ctrl+C[/bold] to quit.\n"
    )

    async def _repl() -> None:
        from rich.prompt import Prompt

        while True:
            try:
                user_input = Prompt.ask(f"[bold cyan]{agent_name}[/bold cyan] >")
            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]Goodbye![/yellow]")
                break

            user_input = user_input.strip()
            if user_input.lower() in ("exit", "quit"):
                console.print("[yellow]Goodbye![/yellow]")
                break
            if not user_input:
                continue

            try:
                response = await agent.chat(user_input, session_id="cli-session")
            except Exception as exc:
                console.print(f"[red]Error:[/] {exc}")
                continue

            console.print(Panel(response, title=agent_name, border_style="blue"))

    asyncio.run(_repl())


# ---------------------------------------------------------------------------
# trace
# ---------------------------------------------------------------------------


@app.command()
def trace(
    checkpoint_file: str = typer.Argument(..., help="Path to a .json checkpoint file"),
) -> None:
    """Display the full message history from a checkpoint JSON file."""
    from agentsdk.persistence.checkpoint import Checkpoint

    path = Path(checkpoint_file)
    if not path.exists():
        console.print(f"[red]File not found:[/] {checkpoint_file}")
        raise typer.Exit(1)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        checkpoint = Checkpoint.model_validate(data)
    except Exception as exc:
        console.print(f"[red]Failed to parse checkpoint:[/] {exc}")
        raise typer.Exit(1)

    table = Table(
        title=f"Session: [bold]{checkpoint.session_id}[/bold]  "
              f"Agent: [bold]{checkpoint.agent_name}[/bold]  "
              f"v{checkpoint.version}",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Role", width=12)
    table.add_column("Content", no_wrap=False, max_width=80)
    table.add_column("Tokens (est.)", justify="right", width=14)

    total_tokens = 0
    for i, msg in enumerate(checkpoint.history, 1):
        role = msg.get("role", "unknown")
        content = msg.get("content") or ""
        truncated = (content[:77] + "...") if len(content) > 80 else content
        tokens = round(len(content.split()) * 1.3)
        total_tokens += tokens
        role_colour = {
            "system": "yellow", "user": "cyan",
            "assistant": "green", "tool": "magenta",
        }.get(role, "white")
        table.add_row(str(i), f"[{role_colour}]{role}[/{role_colour}]", truncated, str(tokens))

    table.add_section()
    table.add_row("", "[bold]Total[/bold]", "", f"[bold]{total_tokens}[/bold]")

    console.print()
    console.print(table)
    console.print(
        f"\n[dim]Created:[/dim] {checkpoint.created_at}  "
        f"[dim]Updated:[/dim] {checkpoint.updated_at}  "
        f"[dim]Iterations:[/dim] {checkpoint.iteration}"
    )


# ---------------------------------------------------------------------------
# list-sessions
# ---------------------------------------------------------------------------


@app.command("list-sessions")
def list_sessions(
    agent_name: str = typer.Argument(..., help="Agent name to list sessions for"),
    base_dir: str = typer.Option(
        ".agentsdk/checkpoints",
        "--base-dir",
        "-d",
        help="Base directory for checkpoints",
    ),
) -> None:
    """List all saved sessions for a named agent."""
    from agentsdk.persistence.file_store import FileCheckpointStore

    async def _run() -> None:
        store = FileCheckpointStore(base_dir=base_dir)
        session_ids = await store.list_sessions(agent_name=agent_name)

        if not session_ids:
            console.print(
                f"[yellow]No sessions found[/yellow] for agent [bold]{agent_name}[/bold] "
                f"in [dim]{base_dir}[/dim]"
            )
            return

        table = Table(
            title=f"Sessions for [bold]{agent_name}[/bold]",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Session ID", style="cyan")
        table.add_column("Created At")
        table.add_column("Updated At")
        table.add_column("Version", justify="right", width=9)
        table.add_column("Messages", justify="right", width=10)

        for sid in sorted(session_ids):
            cp = await store.load(sid)
            if cp is None:
                continue
            table.add_row(
                cp.session_id,
                str(cp.created_at)[:19],
                str(cp.updated_at)[:19],
                str(cp.version),
                str(len(cp.history)),
            )

        console.print()
        console.print(table)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Entry point (direct invocation: python -m agentsdk.cli)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
