# Quickstart

## 1. Install

```bash
pip install agentsdk
```

## 2. Set your API key

```bash
# .env
GROQ_API_KEY=your_key_here
```

## 3. Run your first agent

```python
import asyncio
import os
from dotenv import load_dotenv
from agentsdk import Agent, AgentConfig, GroqProvider

load_dotenv()

async def main():
    agent = Agent(
        config=AgentConfig(
            name="MyAgent",
            system_prompt="You are a helpful assistant.",
        ),
        llm=GroqProvider(api_key=os.environ["GROQ_API_KEY"]),
    )
    result = await agent.run("Explain the GIL in one sentence.")
    print(result.output)

asyncio.run(main())
```

## 4. Add a tool

Five extra lines turn the agent into a tool-using agent.

```python
from agentsdk import tool

@tool
async def add(a: int, b: int) -> str:
    """Add two integers and return the sum as a string."""
    return str(a + b)

agent = Agent(
    config=AgentConfig(name="CalcAgent", system_prompt="Use tools when asked."),
    llm=GroqProvider(api_key=os.environ["GROQ_API_KEY"]),
    tools=[add],
)
result = await agent.run("What is 42 + 58?")
print(result.output)  # "The sum is 100."
```

## 5. Enable persistence

Five extra lines give the agent memory across calls.

```python
from agentsdk import FileCheckpointStore, SessionManager

store = FileCheckpointStore(base_dir=".agentsdk/checkpoints")
session_mgr = SessionManager(store=store, agent_name="MyAgent")

agent = Agent(
    config=AgentConfig(name="MyAgent", system_prompt="You are helpful."),
    llm=GroqProvider(api_key=os.environ["GROQ_API_KEY"]),
    session_manager=session_mgr,
)

# Each call with the same session_id picks up where it left off.
await agent.run("My name is Alice.", session_id="user-42")
result = await agent.run("What is my name?", session_id="user-42")
print(result.output)  # "Your name is Alice."
```
