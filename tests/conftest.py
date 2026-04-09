"""
Shared pytest fixtures and autouse mocks.

RunTracer, fetch_prompt, and embedding functions are automatically mocked for
all tests to prevent real service calls. Tests that specifically test Langfuse
behaviour (e.g. test_harness.py's RunTracer tests) override these mocks as needed.
"""

from unittest.mock import MagicMock, patch

import pytest

TEST_EMBEDDING_DIM = 8


@pytest.fixture(autouse=True)
def clear_langfuse_cache():
    try:
        from weavy.langfuse_client import get_langfuse

        get_langfuse.cache_clear()
        yield
        get_langfuse.cache_clear()
    except ImportError:
        yield


@pytest.fixture(autouse=True)
def mock_run_tracer():
    """Prevent real Langfuse calls from RunTracer in all tests."""
    try:
        from weavy.harness import runner
    except ImportError:
        yield None
        return

    mock = MagicMock()
    mock.get_trace_id.return_value = "mock-trace-id"
    with patch.object(runner, "RunTracer", return_value=mock):
        yield mock


@pytest.fixture(autouse=True)
def mock_fetch_prompt():
    """Mock prompt loading to avoid filesystem dependency in tests."""
    try:
        from weavy.services import workflow
    except ImportError:
        yield None
        return

    with patch.object(
        workflow, "fetch_prompt", return_value="(mocked system prompt)"
    ) as mock:
        yield mock


@pytest.fixture(autouse=True)
def mock_embeddings():
    """Mock embedding calls to avoid real LiteLLM/Gemini calls in tests."""
    try:
        from weavy.services import embedding
    except ImportError:
        yield None
        return

    dummy_vec = [0.1] * TEST_EMBEDDING_DIM
    with (
        patch.object(embedding, "embed", return_value=dummy_vec),
        patch.object(embedding, "embed_node", return_value=dummy_vec),
        patch.object(embedding, "get_dimension", return_value=TEST_EMBEDDING_DIM),
    ):
        yield
