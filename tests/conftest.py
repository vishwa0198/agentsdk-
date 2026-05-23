"""tests/conftest.py — pytest configuration for agentsdk test suite."""

import sys
from pathlib import Path

import pytest

# Make webui/backend importable so test_pipeline.py / test_mcp.py can import
# models, pipeline_manager, mcp_manager, etc.
_BACKEND = Path(__file__).parent.parent / "webui" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require GROQ_API_KEY)",
    )
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except ImportError:
        pass
