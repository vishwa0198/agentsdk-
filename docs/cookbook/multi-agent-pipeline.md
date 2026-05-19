# Multi-agent Pipeline

Three-node DAG: **Researcher → Analyst → Writer**. Each node receives the previous node's output via `data_map`.

```python
# pipeline.py
import asyncio
import os
from dotenv import load_dotenv
from agentsdk import Agent, AgentConfig, GroqProvider, DEFAULT_TOOLS
from agentsdk import AgentGraph, AgentNode, Edge, GraphRunner

load_dotenv()
llm = GroqProvider(api_key=os.environ["GROQ_API_KEY"])


def make_agent(name: str, prompt: str) -> Agent:
    return Agent(
        config=AgentConfig(name=name, system_prompt=prompt, max_iterations=3),
        llm=llm,
        registry=DEFAULT_TOOLS,
    )


researcher = make_agent(
    "Researcher",
    "You are a researcher. Given a topic, produce 5 bullet-point facts about it.",
)
analyst = make_agent(
    "Analyst",
    "You are an analyst. Given bullet points, identify the 2 most important insights.",
)
writer = make_agent(
    "Writer",
    "You are a writer. Turn the insights you receive into one polished paragraph.",
)

# Build the graph
graph = AgentGraph()
graph.add_node(AgentNode(node_id="researcher", agent=researcher))
graph.add_node(AgentNode(node_id="analyst",    agent=analyst))
graph.add_node(AgentNode(node_id="writer",     agent=writer))

graph.add_edge(Edge(from_node="researcher", to_node="analyst",
                    data_map={"output": "input"}))
graph.add_edge(Edge(from_node="analyst",    to_node="writer",
                    data_map={"output": "input"}))

graph.set_entry("researcher")
graph.set_exit("writer")


async def main():
    runner = GraphRunner(graph)
    result = await runner.run({"input": "The impact of large language models on software engineering"})
    print("=== Final Article ===")
    print(result["output"])


asyncio.run(main())
```

## Running it

```bash
python pipeline.py
```

Expected flow:

1. **Researcher** receives the topic, returns 5 bullet points
2. **Analyst** receives the bullets, returns 2 key insights
3. **Writer** receives the insights, returns a polished paragraph

Each stage's `output` key is forwarded as the next stage's `input` key via `data_map={"output": "input"}`.
