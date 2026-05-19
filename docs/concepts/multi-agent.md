# Multi-agent

agentsdk has two multi-agent primitives: a **DAG pipeline** (deterministic, sequential/parallel) and an **async message bus** (dynamic, event-driven delegation).

## AgentGraph — DAG pipeline

Wire agents into a directed acyclic graph. Nodes on the same level run in parallel.

```python
import asyncio, os
from dotenv import load_dotenv
from agentsdk import Agent, AgentConfig, GroqProvider
from agentsdk import AgentGraph, AgentNode, Edge, GraphRunner

load_dotenv()
llm = GroqProvider(api_key=os.environ["GROQ_API_KEY"])

researcher = Agent(config=AgentConfig(name="Researcher",
    system_prompt="Summarise the topic given to you in 3 bullet points."), llm=llm)
writer = Agent(config=AgentConfig(name="Writer",
    system_prompt="Turn the bullet points you receive into one polished paragraph."), llm=llm)

r_node = AgentNode(node_id="researcher", agent=researcher)
w_node = AgentNode(node_id="writer",     agent=writer)

graph = AgentGraph()
graph.add_node(r_node)
graph.add_node(w_node)
# Pass researcher's "output" key as writer's "input" key
graph.add_edge(Edge(from_node="researcher", to_node="writer",
                    data_map={"output": "input"}))
graph.set_entry("researcher")
graph.set_exit("writer")

async def main():
    runner = GraphRunner(graph)
    result = await runner.run({"input": "Explain async/await in Python"})
    print(result["output"])

asyncio.run(main())
```

### `data_map` rules

| Value | Behaviour |
|---|---|
| `{}` (empty, default) | Pass the full parent output dict unchanged |
| `{"output": "input"}` | Rename key `output` → `input` before passing |

## MessageBus — dynamic delegation

`BusAwareAgent` can delegate work to peers at runtime through the LLM's tool calls.

```python
import asyncio, os
from dotenv import load_dotenv
from agentsdk import AgentConfig, GroqProvider
from agentsdk import MessageBus, BusAwareAgent, BusRunner

load_dotenv()
llm = GroqProvider(api_key=os.environ["GROQ_API_KEY"])

bus = MessageBus()

manager = BusAwareAgent(
    config=AgentConfig(name="Manager",
        system_prompt="Delegate maths questions to the calculator agent."),
    llm=llm, bus=bus, node_id="manager")

calc = BusAwareAgent(
    config=AgentConfig(name="Calculator",
        system_prompt="Answer maths questions with exact numbers."),
    llm=llm, bus=bus, node_id="calculator")

async def main():
    runner = BusRunner(bus, agents={"manager": manager, "calculator": calc})
    async with runner:
        result = await manager.run("Ask the calculator: what is 99 * 77?")
        print(result.output)

asyncio.run(main())
```
