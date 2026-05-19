# Installation

## Requirements

- Python 3.12+
- A [Groq API key](https://console.groq.com) (free tier available)

## Install the package

```bash
pip install agentsdk
```

## Optional extras

```bash
# With OpenTelemetry tracing
pip install agentsdk[otel]

# With dev tools (pytest, dotenv)
pip install agentsdk[dev]
```

## Set your API key

Create a `.env` file in your project root:

```bash
GROQ_API_KEY=your_key_here
```

Or export it in your shell:

```bash
export GROQ_API_KEY=your_key_here
```

## Scaffold a new project

```bash
scaffold-agent new myproject
cd myproject
python main.py
```
