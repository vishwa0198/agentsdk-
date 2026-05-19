# Research Agent

An agent that fetches a URL and summarises its content. Uses `http_request` and `run_python` from `DEFAULT_TOOLS`.

```python
# research_agent.py
import asyncio
import os
from dotenv import load_dotenv
from agentsdk import Agent, AgentConfig, GroqProvider, DEFAULT_TOOLS

load_dotenv()

agent = Agent(
    config=AgentConfig(
        name="Researcher",
        system_prompt=(
            "You are a research assistant. When given a topic or URL, "
            "use http_request to fetch the page, then summarise the key points "
            "in 3–5 bullet points. Be concise and factual."
        ),
        max_iterations=4,
        verbose=True,
    ),
    llm=GroqProvider(api_key=os.environ["GROQ_API_KEY"]),
    registry=DEFAULT_TOOLS,
)


async def research(topic: str) -> str:
    result = await agent.run(topic)
    return result.output


async def main():
    # Research from a live URL
    summary = await research(
        "Fetch https://httpbin.org/json and summarise what the response contains."
    )
    print("=== Research Summary ===")
    print(summary)

    # Research using Python computation
    code_result = await research(
        "Use run_python to compute the first 10 Fibonacci numbers and list them."
    )
    print("\n=== Code Result ===")
    print(code_result)


asyncio.run(main())
```

## Running it

```bash
python research_agent.py
```

Expected: the agent calls `http_request`, receives the JSON, then writes a bullet-point summary. The second call uses `run_python` to compute the sequence and reports back.
