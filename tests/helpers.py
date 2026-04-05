import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

from falkordb import Graph

from weavy.models.canonical import Transcript
from weavy.store import canonical as store_canonical
from weavy.store.client import get_graph
from weavy.store.system import increment_counter, init_system

TEST_GRAPH = "weavy_test"


def reset_test_graph(*extra_labels: str) -> Graph:
    """Reset the shared FalkorDB test graph and reinitialize system state."""
    graph = get_graph(TEST_GRAPH)
    graph.query("MATCH (s:System) DELETE s")
    graph.query("MATCH (n:SemanticNode) DETACH DELETE n")
    for label in extra_labels:
        graph.query(f"MATCH (n:{label}) DETACH DELETE n")
    init_system(graph)
    return graph


def store_test_transcript(graph: Any, text: str) -> str:
    """Create a transcript record for integration-style tests."""
    rec_id = increment_counter(graph, "rec")
    store_canonical.create_transcript(
        graph,
        Transcript(
            id=rec_id,
            audio_path="/dev/null",
            timestamp=datetime.now(tz=timezone.utc),
            text=text,
        ),
    )
    return rec_id


def mock_tool_response(
    tool_name: str,
    args: dict[str, Any],
    call_id: str = "tc-1",
    *,
    usage: dict[str, int] | None = None,
) -> MagicMock:
    """Build a mock litellm response for a single tool call."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = tool_name
    tc.function.arguments = json.dumps(args)

    msg = MagicMock()
    msg.tool_calls = [tc]
    msg.content = None
    msg.reasoning_content = None

    choice = MagicMock()
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    if usage is None:
        resp.usage = None
        return resp

    usage_mock = MagicMock()
    usage_mock.prompt_tokens = usage.get("prompt_tokens", 0)
    usage_mock.completion_tokens = usage.get("completion_tokens", 0)
    usage_mock.total_tokens = usage.get("total_tokens", 0)
    usage_mock.completion_tokens_details = usage.get("completion_tokens_details")
    resp.usage = usage_mock
    return resp
