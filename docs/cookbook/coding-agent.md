# Coding Agent

An agent that writes a Python script to disk, executes it, and reports the output. Uses `write_file` and `run_python` from `DEFAULT_TOOLS`.

```python
# coding_agent.py
import asyncio
import os
from dotenv import load_dotenv
from agentsdk import Agent, AgentConfig, GroqProvider, DEFAULT_TOOLS

load_dotenv()

agent = Agent(
    config=AgentConfig(
        name="CodingAgent",
        system_prompt=(
            "You are a coding assistant. When given a task:\n"
            "1. Write the solution as a Python script using write_file.\n"
            "2. Execute it with run_python and report the output.\n"
            "3. If the output has an error, fix the script and re-run.\n"
            "Keep scripts under 20 lines."
        ),
        max_iterations=6,
        verbose=True,
    ),
    llm=GroqProvider(api_key=os.environ["GROQ_API_KEY"]),
    registry=DEFAULT_TOOLS,
)


async def code(task: str) -> str:
    result = await agent.run(task)
    return result.output


async def main():
    output = await code(
        "Write a Python script that prints all prime numbers up to 50, "
        "save it as primes.py, then run it and tell me the output."
    )
    print("=== Agent Output ===")
    print(output)


asyncio.run(main())
```

## Running it

```bash
python coding_agent.py
```

Expected flow:

1. Agent calls `write_file` → creates `primes.py`
2. Agent calls `run_python` with the file's content → captures stdout
3. Agent reports: *"The primes up to 50 are: 2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47"*
