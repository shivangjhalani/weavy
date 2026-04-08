"""
Phase 7 tests — Query/chat mode.
Mocks litellm.completion to avoid real LLM calls.
Uses the "weavy_test" graph to avoid touching the main graph.
"""

import json
from unittest.mock import patch

import pytest
from falkordb import Graph

from weavy.models.graph import ProvenanceInput
from weavy.store import canonical as store_canonical
from tests.helpers import mock_tool_response, reset_test_graph, store_test_transcript

SAMPLE_TRANSCRIPT = (
    "[0:00] I've been thinking about changing jobs a lot lately.\n"
    "[0:14] The mortgage scares me but I'm feeling trapped.\n"
)


@pytest.fixture
def graph() -> Graph:
    return reset_test_graph("Theme", "Transcript", "ChatSession")


# ---------------------------------------------------------------------------
# run_query
# ---------------------------------------------------------------------------


def test_query_delivers_response(graph: Graph) -> None:
    """Agent calls deliver_response; trace is completed with answer in payload."""
    rec_id = store_test_transcript(graph, SAMPLE_TRANSCRIPT)

    deliver_args = {
        "answer": "You have been thinking about changing jobs.",
        "cited_sources": [{"source_id": rec_id, "start_offset": 0, "end_offset": 14}],
        "consulted_nodes": [],
    }
    done_resp = mock_tool_response("deliver_response", deliver_args)

    with (
        patch("weavy.modes.query.get_graph", return_value=graph),
        patch("litellm.completion", return_value=done_resp),
    ):
        from weavy.modes.query import run_query

        trace = run_query("What have I been thinking about?")

    assert trace.status == "completed"
    assert (
        trace.completion_payload["answer"]
        == "You have been thinking about changing jobs."
    )
def test_query_creates_chat_session(graph: Graph) -> None:
    """A ChatSession record is persisted in the store after a completed query run."""
    store_test_transcript(graph, SAMPLE_TRANSCRIPT)

    deliver_args = {
        "answer": "You have been thinking about changing jobs.",
        "cited_sources": [],
        "consulted_nodes": [],
    }
    done_resp = mock_tool_response("deliver_response", deliver_args)

    with (
        patch("weavy.modes.query.get_graph", return_value=graph),
        patch("litellm.completion", return_value=done_resp),
    ):
        from weavy.modes.query import run_query

        trace = run_query("What have I been thinking about?")

    assert trace.status == "completed"

    # ChatSession should exist in the store
    result = graph.query("MATCH (c:ChatSession) RETURN c.id ORDER BY c.id")
    assert result.result_set, "No ChatSession node found in store"
    chat_id = result.result_set[0][0]
    assert chat_id.startswith("chat:")

    session = store_canonical.get_chat_session(graph, chat_id)
    assert session.id == chat_id
def test_query_rejects_ingestion_provenance(graph: Graph) -> None:
    """Agent calling create_node with rec:N provenance in query mode fails the run."""
    rec_id = store_test_transcript(graph, SAMPLE_TRANSCRIPT)

    # rec:N provenance is forbidden in query mode
    bad_prov = ProvenanceInput(source_id=rec_id, start_offset=0, end_offset=14)
    bad_args = {
        "aliases": ["concept"],
        "summary": "Some concept.",
        "note": "Wrong provenance mode.",
        "provenance": bad_prov.model_dump(),
    }
    bad_resp = mock_tool_response("create_node", bad_args)

    with (
        patch("weavy.modes.query.get_graph", return_value=graph),
        patch("litellm.completion", return_value=bad_resp),
    ):
        from weavy.modes.query import run_query

        trace = run_query("Test question.")

    assert trace.status == "failed"
    assert trace.touched_nodes == []
def test_query_conversation_captured(graph: Graph) -> None:
    """trace.conversation is populated with non-system messages after the run."""
    store_test_transcript(graph, SAMPLE_TRANSCRIPT)

    deliver_args = {
        "answer": "Yes, career anxiety is a recurring theme.",
        "cited_sources": [],
        "consulted_nodes": [],
    }
    done_resp = mock_tool_response("deliver_response", deliver_args)

    with (
        patch("weavy.modes.query.get_graph", return_value=graph),
        patch("litellm.completion", return_value=done_resp),
    ):
        from weavy.modes.query import run_query

        trace = run_query("Am I anxious about my career?")

    assert trace.conversation is not None
    roles = [m["role"] for m in trace.conversation]
    assert "system" not in roles
    assert "user" in roles
    assert "tool" not in roles
    assert "tool_call_id" not in json.dumps(trace.conversation)
