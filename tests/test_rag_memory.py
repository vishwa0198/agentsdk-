"""RAG memory end-to-end validation script."""
import os
import pytest
from dotenv import load_dotenv

load_dotenv(override=True)

from agentsdk.agent import Agent, AgentConfig
from agentsdk.llm import OllamaProvider
from agentsdk.memory.vector_store import VectorMemoryStore
from agentsdk.memory.rag_memory import RAGMemory


@pytest.mark.asyncio
@pytest.mark.integration
async def test_rag_memory_integration():
    store = VectorMemoryStore(collection_name="test-agent")
    memory = RAGMemory(store=store, max_messages=20)

    llm = OllamaProvider()
    config = AgentConfig(
        name="RAGAgent",
        system_prompt="You are a helpful assistant with semantic memory.",
        verbose=True,
    )
    agent = Agent(config=config, llm=llm, memory=memory)

    SESSION = "rag-test-001"

    # Turn 1 — store a fact
    r1 = await agent.run("My dog's name is Biscuit and he is a golden retriever.", session_id=SESSION)
    print("\nTurn 1:", r1.output)

    # Turn 2 — store another fact
    r2 = await agent.run("I live in Chennai and work as a software engineer.", session_id=SESSION)
    print("\nTurn 2:", r2.output)

    # Turn 3 — semantic retrieval test
    r3 = await agent.run("What do you know about my pet?", session_id=SESSION)
    print("\nTurn 3:", r3.output)
    # Expected: recalls Biscuit the golden retriever via semantic search

    # Turn 4 — another semantic retrieval
    r4 = await agent.run("What city am I from?", session_id=SESSION)
    print("\nTurn 4:", r4.output)
    # Expected: recalls Chennai

    # Clean up the test session from the store
    await store.delete_session(SESSION)
    print("\n[Cleanup] Deleted session from vector store.")

    print("\n=== All turns completed successfully ===")
