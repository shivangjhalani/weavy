"""
Phase 7 tests — Query/chat mode.
Mocks litellm.completion to avoid real LLM calls.
Uses the "arakne_test" graph to avoid touching the main graph.
"""

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from falkordb import Graph

from arakne.models.canonical import Transcript
from arakne.models.graph import ProvenanceInput
from arakne.models.traces import TouchedNode
from arakne.store import canonical as store_canonical
from arakne.store import graph as store_graph
from arakne.store.client import get_graph
from arakne.store.system import increment_counter, init_system

TEST_GRAPH = "arakne_test"

SAMPLE_TRANSCRIPT = (
    "[0:00] I've been thinking about changing jobs a lot lately.\n"
    "[0:14] The mortgage scares me but I'm feeling trapped.\n"
)


@pytest.fixture
def graph() -> Graph:
    g = get_graph(TEST_GRAPH)
    g.query("MATCH (s:System) DELETE s")
    g.query("MATCH (n:SemanticNode) DETACH DELETE n")
    g.query("MATCH (t:Theme) DETACH DELETE t")
    g.query("MATCH (t:Transcript) DELETE t")
    g.query("MATCH (c:ChatSession) DELETE c")
    init_system(g)
    return g


def _store_transcript(graph: Graph, text: str = SAMPLE_TRANSCRIPT) -> str:
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


def _mock_response(tool_name: str, args: dict[str, Any], call_id: str = "tc-1") -> MagicMock:
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = tool_name
    tc.function.arguments = json.dumps(args)

    msg = MagicMock()
    msg.tool_calls = [tc]
    msg.content = None

    choice = MagicMock()
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# run_query
# ---------------------------------------------------------------------------


def test_query_delivers_response(graph: Graph) -> None:
    """Agent calls deliver_response; trace is completed with answer in payload."""
    rec_id = _store_transcript(graph)

    deliver_args = {
        "answer": "You have been thinking about changing jobs.",
        "cited_sources": [{"source_id": rec_id, "start_offset": 0, "end_offset": 14}],
        "consulted_nodes": [],
    }
    done_resp = _mock_response("deliver_response", deliver_args)

    with (
        patch("arakne.modes.query.get_graph", return_value=graph),
        patch("arakne.modes.query.theme_mode.run_theme_update") as mock_theme,
        patch("litellm.completion", return_value=done_resp),
        patch("arakne.modes.query.save_trace"),
    ):
        from arakne.modes.query import run_query

        trace = run_query("What have I been thinking about?")

    assert trace.status == "completed"
    assert trace.completion_payload["answer"] == "You have been thinking about changing jobs."
    mock_theme.assert_not_called()  # no graph writes → no theme pass


def test_query_creates_chat_session(graph: Graph) -> None:
    """A ChatSession record is persisted in the store after a completed query run."""
    _store_transcript(graph)

    deliver_args = {
        "answer": "You have been thinking about changing jobs.",
        "cited_sources": [],
        "consulted_nodes": [],
    }
    done_resp = _mock_response("deliver_response", deliver_args)

    with (
        patch("arakne.modes.query.get_graph", return_value=graph),
        patch("arakne.modes.query.theme_mode.run_theme_update"),
        patch("litellm.completion", return_value=done_resp),
        patch("arakne.modes.query.save_trace"),
    ):
        from arakne.modes.query import run_query

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
    rec_id = _store_transcript(graph)

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
        "cited_sources": [{"source_id": fixed_chat_id, "start_offset": 0, "end_offset": None}],
        "consulted_nodes": [],
    }

    create_resp = _mock_response("create_node", create_args, "tc-1")
    done_resp = _mock_response("deliver_response", deliver_args, "tc-2")

    with (
        patch("arakne.modes.query.get_graph", return_value=graph),
        patch("arakne.modes.query.theme_mode.run_theme_update") as mock_theme,
        patch("arakne.store.system.increment_counter", return_value=fixed_chat_id),
        patch("litellm.completion", side_effect=[create_resp, done_resp]),
        patch("arakne.modes.query.save_trace"),
    ):
        from arakne.modes.query import run_query

        trace = run_query("I just decided to leave my job.")

    assert trace.status == "completed"
    assert len(trace.touched_nodes) == 1
    assert trace.touched_nodes[0].action == "created"
    mock_theme.assert_called_once()


def test_query_rejects_ingestion_provenance(graph: Graph) -> None:
    """Agent calling create_node with rec:N provenance in query mode fails the run."""
    rec_id = _store_transcript(graph)

    # rec:N provenance is forbidden in query mode
    bad_prov = ProvenanceInput(source_id=rec_id, start_offset=0, end_offset=14)
    bad_args = {
        "aliases": ["concept"],
        "summary": "Some concept.",
        "note": "Wrong provenance mode.",
        "provenance": bad_prov.model_dump(),
    }
    bad_resp = _mock_response("create_node", bad_args)

    with (
        patch("arakne.modes.query.get_graph", return_value=graph),
        patch("arakne.modes.query.theme_mode.run_theme_update"),
        patch("litellm.completion", return_value=bad_resp),
        patch("arakne.modes.query.save_trace"),
    ):
        from arakne.modes.query import run_query

        trace = run_query("Test question.")

    assert trace.status == "failed"
    assert trace.touched_nodes == []


def test_query_no_writes_skips_theme(graph: Graph) -> None:
    """deliver_response with no graph writes does not trigger theme mode."""
    _store_transcript(graph)

    deliver_args = {
        "answer": "Nothing to update.",
        "cited_sources": [],
        "consulted_nodes": [],
    }
    done_resp = _mock_response("deliver_response", deliver_args)

    with (
        patch("arakne.modes.query.get_graph", return_value=graph),
        patch("arakne.modes.query.theme_mode.run_theme_update") as mock_theme,
        patch("litellm.completion", return_value=done_resp),
        patch("arakne.modes.query.save_trace"),
    ):
        from arakne.modes.query import run_query

        trace = run_query("Anything new?")

    assert trace.status == "completed"
    assert trace.touched_nodes == []
    mock_theme.assert_not_called()


def test_query_conversation_captured(graph: Graph) -> None:
    """trace.conversation is populated with non-system messages after the run."""
    _store_transcript(graph)

    deliver_args = {
        "answer": "Yes, career anxiety is a recurring theme.",
        "cited_sources": [],
        "consulted_nodes": [],
    }
    done_resp = _mock_response("deliver_response", deliver_args)

    with (
        patch("arakne.modes.query.get_graph", return_value=graph),
        patch("arakne.modes.query.theme_mode.run_theme_update"),
        patch("litellm.completion", return_value=done_resp),
        patch("arakne.modes.query.save_trace"),
    ):
        from arakne.modes.query import run_query

        trace = run_query("Am I anxious about my career?")

    assert trace.conversation is not None
    roles = [m["role"] for m in trace.conversation]
    assert "system" not in roles
    assert "user" in roles
