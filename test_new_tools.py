import asyncio, os
from dotenv import load_dotenv
from agentsdk.agent import Agent, AgentConfig
from agentsdk.llm import GroqProvider
from agentsdk.tools.builtin import DEFAULT_TOOLS

load_dotenv()

async def test():
    llm = GroqProvider(api_key=os.environ["GROQ_API_KEY"])
    config = AgentConfig(
        name="ToolsAgent",
        system_prompt="You are a helpful assistant. Use tools when needed.",
        verbose=True,
    )
    agent = Agent(config=config, llm=llm, registry=DEFAULT_TOOLS)

    # Test 1 — GitHub
    r1 = await agent.run("Get info about the github repo 'torvalds/linux'")
    print("\n=== Test 1 (GitHub) ===")
    print(r1.output)

    # Test 2 — Web scraping
    r2 = await agent.run("Scrape https://example.com and tell me what it says")
    print("\n=== Test 2 (Web scraping) ===")
    print(r2.output)

    # Test 3 — SQL (SQLite)
    r3 = await agent.run(
        "Create a SQLite database at /tmp/test.db, create a users table with id and name columns, "
        "insert 3 users, then query all of them."
    )
    print("\n=== Test 3 (SQL) ===")
    print(r3.output)

asyncio.run(test())
