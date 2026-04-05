"""
Shared pytest fixtures and autouse mocks.

RunTracer and fetch_prompt are automatically mocked for all tests to prevent
real Langfuse calls. Tests that specifically test Langfuse behaviour (e.g.
test_harness.py's RunTracer tests) override these mocks as needed.
"""

from unittest.mock import MagicMock, patch

import pytest

from arakne.langfuse_client import get_langfuse


@pytest.fixture(autouse=True)
def clear_langfuse_cache():
    get_langfuse.cache_clear()
    yield
    get_langfuse.cache_clear()


@pytest.fixture(autouse=True)
def mock_run_tracer():
    """Prevent real Langfuse calls from RunTracer in all tests."""
    try:
        from arakne.harness import runner
    except ImportError:
        yield None
        return

    mock = MagicMock()
    mock.get_trace_id.return_value = "mock-trace-id"
    with patch.object(runner, "RunTracer", return_value=mock):
        yield mock


@pytest.fixture(autouse=True)
def mock_fetch_prompt():
    """Prevent real Langfuse prompt fetches in all tests."""
    try:
        from arakne.modes import _common
    except ImportError:
        yield None
        return

    with patch.object(_common, "fetch_prompt", return_value="(mocked system prompt)") as mock:
        yield mock
