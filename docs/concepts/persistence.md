# Persistence

agentsdk saves conversation history as JSON checkpoints on disk. Sessions survive process restarts and can be forked.

## Basic setup

```python
import os
from dotenv import load_dotenv
from agentsdk import Agent, AgentConfig, GroqProvider
from agentsdk import FileCheckpointStore, SessionManager

load_dotenv()

store = FileCheckpointStore(base_dir=".agentsdk/checkpoints")
session_mgr = SessionManager(store=store, agent_name="MyAgent")

agent = Agent(
    config=AgentConfig(name="MyAgent", system_prompt="You are helpful."),
    llm=GroqProvider(api_key=os.environ["GROQ_API_KEY"]),
    session_manager=session_mgr,
)
```

## Multi-turn session

Pass the same `session_id` across calls — the agent resumes exactly where it left off.

```python
import asyncio

async def main():
    sid = "user-42"

    await agent.run("My name is Alice.", session_id=sid)
    await agent.run("I work at Acme Corp.", session_id=sid)
    result = await agent.run("What do you know about me?", session_id=sid)
    print(result.output)  # Recalls name and employer

asyncio.run(main())
```

Checkpoints are stored at:

```
.agentsdk/checkpoints/MyAgent/user-42.json
```

## Fork a session

Create a branch from an existing session — useful for A/B testing prompts or exploring alternatives.

```python
forked_id = await session_mgr.fork("user-42", new_session_id="user-42-fork")
# user-42-fork has the same history as user-42 but is independent going forward
```

## Inspect with the CLI

```bash
# List all sessions for an agent
scaffold-agent list-sessions MyAgent

# Pretty-print a checkpoint's message history
scaffold-agent trace .agentsdk/checkpoints/MyAgent/user-42.json
```

The `trace` command shows a table with role, content preview, and per-message token estimates.

## Checkpoint file layout

```json
{
  "session_id": "user-42",
  "agent_name": "MyAgent",
  "history": [...],
  "iteration": 3,
  "metadata": {"stopped_by": "end_turn"},
  "version": 3,
  "created_at": "2026-05-19T10:00:00Z",
  "updated_at": "2026-05-19T10:05:00Z"
}
```
