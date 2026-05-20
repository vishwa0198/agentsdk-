"""tests/conftest.py — pytest configuration for agentsdk test suite."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require GROQ_API_KEY)",
    )
    # Load .env before any test module is imported so GROQ_API_KEY is available
    # when test_integration.py evaluates groq_key at module level.
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)  # override stale shell env vars with .env values
    except ImportError:
        pass  # python-dotenv not installed — rely on shell env
