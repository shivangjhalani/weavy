"""
Phase 7 tests — Query/chat mode.
Mocks litellm.completion to avoid real LLM calls.
Uses the "weavy_test" graph to avoid touching the main graph.
"""

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
        patch("weavy.modes.theme.run_theme_update") as mock_theme,
        patch("litellm.completion", return_value=done_resp),
    ):
        from weavy.modes.query import run_query

        trace = run_query("What have I been thinking about?")

    assert trace.status == "completed"
    assert (
        trace.completion_payload["answer"]
        == "You have been thinking about changing jobs."
    )
    mock_theme.assert_not_called()  # no graph writes → no theme pass


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
        patch("weavy.modes.theme.run_theme_update"),
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


def test_query_with_graph_write_triggers_theme(graph: Graph) -> None:
    """Graph write during query triggers a post-run theme update."""
    store_test_transcript(graph, SAMPLE_TRANSCRIPT)

    # First mint a chat id to use as provenance in the write
    # (the mode itself will mint the actual chat id - we just need the write to succeed)
    # We need to set up a node write with a valid chat:N provenance.
    # The harness will use the trace.mode="query" to validate chat:N provenance.

    # We'll simulate: agent creates a node with chat provenance, then delivers response.
    # But to get a valid chat:N, we let the mode mint it — the agent's provenance must
    # match whatever chat:N gets minted. In the mock we use a wildcard approach:
    # we pre-mint a chat id and patch increment_counter to return it consistently.

    fixed_chat_id = "chat:1"

    prov = ProvenanceInput(source_id=fixed_chat_id, start_offset=0, end_offset=None)
    create_args = {
        "aliases": ["job change"],
        "summary": "User confirmed they are leaving their job.",
        "note": "User stated this directly in chat.",
        "provenance": prov.model_dump(),
    }
    deliver_args = {
        "answer": "Noted — updated graph with your correction.",
        "cited_sources": [
            {"source_id": fixed_chat_id, "start_offset": 0, "end_offset": None}
        ],
        "consulted_nodes": [],
    }

    create_resp = mock_tool_response("create_node", create_args, "tc-1")
    done_resp = mock_tool_response("deliver_response", deliver_args, "tc-2")

    with (
        patch("weavy.modes.query.get_graph", return_value=graph),
        patch("weavy.modes.theme.run_theme_update") as mock_theme,
        patch("weavy.store.system.increment_counter", return_value=fixed_chat_id),
        patch("litellm.completion", side_effect=[create_resp, done_resp]),
    ):
        from weavy.modes.query import run_query

        trace = run_query("I just decided to leave my job.")

    assert trace.status == "completed"
    assert len(trace.touched_nodes) == 1
    assert trace.touched_nodes[0].action == "created"
    mock_theme.assert_called_once()


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
        patch("weavy.modes.theme.run_theme_update"),
        patch("litellm.completion", return_value=bad_resp),
    ):
        from weavy.modes.query import run_query

        trace = run_query("Test question.")

    assert trace.status == "failed"
    assert trace.touched_nodes == []


def test_query_no_writes_skips_theme(graph: Graph) -> None:
    """deliver_response with no graph writes does not trigger theme mode."""
    store_test_transcript(graph, SAMPLE_TRANSCRIPT)

    deliver_args = {
        "answer": "Nothing to update.",
        "cited_sources": [],
        "consulted_nodes": [],
    }
    done_resp = mock_tool_response("deliver_response", deliver_args)

    with (
        patch("weavy.modes.query.get_graph", return_value=graph),
        patch("weavy.modes.theme.run_theme_update") as mock_theme,
        patch("litellm.completion", return_value=done_resp),
    ):
        from weavy.modes.query import run_query

        trace = run_query("Anything new?")

    assert trace.status == "completed"
    assert trace.touched_nodes == []
    mock_theme.assert_not_called()


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
        patch("weavy.modes.theme.run_theme_update"),
        patch("litellm.completion", return_value=done_resp),
    ):
        from weavy.modes.query import run_query

        trace = run_query("Am I anxious about my career?")

    assert trace.conversation is not None
    roles = [m["role"] for m in trace.conversation]
    assert "system" not in roles
    assert "user" in roles
