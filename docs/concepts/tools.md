# Tools

## The `@tool` decorator

Decorate any `async` function to create a tool. The docstring becomes the LLM's description; parameter type hints become the JSON Schema.

```python
from agentsdk import tool

@tool
async def celsius_to_fahrenheit(celsius: float) -> str:
    """Convert a temperature from Celsius to Fahrenheit."""
    return str(celsius * 9 / 5 + 32)
```

agentsdk inspects the signature and auto-generates:

```json
{
  "name": "celsius_to_fahrenheit",
  "description": "Convert a temperature from Celsius to Fahrenheit.",
  "parameters": {
    "type": "object",
    "properties": {
      "celsius": {"type": "number"}
    },
    "required": ["celsius"]
  }
}
```

Supported type annotations: `str`, `int`, `float`, `bool`, `dict`, `list[X]`, `Optional[X]` / `X | None`.

## ToolRegistry

Group tools and pass them as a unit to an agent.

```python
from agentsdk import ToolRegistry, tool

registry = ToolRegistry()

@tool
async def greet(name: str) -> str:
    """Greet a person by name."""
    return f"Hello, {name}!"

@tool
async def add(a: int, b: int) -> str:
    """Add two integers."""
    return str(a + b)

registry.register(greet)
registry.register(add)

# Pass to agent
agent = Agent(config=config, llm=llm, registry=registry)
```

## Passing tools to an agent

Three equivalent ways:

```python
# Flat list
agent = Agent(config=config, llm=llm, tools=[greet, add])

# Registry
agent = Agent(config=config, llm=llm, registry=registry)

# Both — merged, registry tools appended after flat list
agent = Agent(config=config, llm=llm, tools=[greet], registry=registry)
```

## Built-in tools

`DEFAULT_TOOLS` ships five ready-made tools:

```python
from agentsdk import DEFAULT_TOOLS

agent = Agent(config=config, llm=llm, registry=DEFAULT_TOOLS)
```

| Tool | What it does |
|---|---|
| `http_request` | `GET` a URL, return truncated response body |
| `read_file` | Read a local file (rejects `..` paths) |
| `write_file` | Write content to a local file |
| `run_python` | Execute Python code in a subprocess (10 s timeout) |
| `get_datetime` | Return the current UTC datetime string |
