"""
Phase 5 + 6 tests — Ingestion flow, theme mode, and fence creation.
Mocks litellm.completion to avoid real LLM calls.
Uses the "arakne_test" graph to avoid touching the main graph.
"""

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from falkordb import Graph

from arakne.config import settings
from arakne.models.canonical import Transcript
from arakne.models.graph import FenceEntry, ProvenanceInput
from arakne.models.traces import TouchedNode
from arakne.store import canonical as store_canonical
from arakne.store import graph as store_graph
from arakne.store import themes as store_themes
from arakne.store.client import get_graph
from arakne.store.system import get_system, increment_counter, init_system

TEST_GRAPH = "arakne_test"

SAMPLE_TRANSCRIPT = (
    "[0:00] I've been thinking about changing jobs a lot lately.\n"
    "[0:14] The mortgage scares me but I'm feeling trapped.\n"
    "[0:28] Had a great talk with my mentor yesterday about risk.\n"
)


@pytest.fixture
def graph() -> Graph:
    g = get_graph(TEST_GRAPH)
    g.query("MATCH (s:System) DELETE s")
    g.query("MATCH (n:SemanticNode) DETACH DELETE n")
    g.query("MATCH (t:Theme) DETACH DELETE t")
    g.query("MATCH (t:Transcript) DELETE t")
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
# run_ingestion
# ---------------------------------------------------------------------------


def test_ingest_into_empty_graph(graph: Graph) -> None:
    """Agent creates a node then calls complete_ingestion; node appears in graph."""
    rec_id = _store_transcript(graph)

    prov = ProvenanceInput(source_id=rec_id, start_offset=0, end_offset=14)
    create_args = {
        "aliases": ["job change"],
        "summary": "Contemplating leaving current job.",
        "note": "First mention — feels trapped, mortgage a barrier.",
        "provenance": prov.model_dump(),
    }
    completion_args = {"summary": "Ingested a transcript about career anxiety."}

    create_resp = _mock_response("create_node", create_args, "tc-1")
    done_resp = _mock_response("complete_ingestion", completion_args, "tc-2")

    with (
        patch("arakne.modes.ingestion.get_graph", return_value=graph),
        patch("arakne.modes.ingestion.theme_mode.run_theme_update") as mock_theme,
        patch("litellm.completion", side_effect=[create_resp, done_resp]),
        patch("arakne.modes.ingestion.save_trace"),
    ):
        from arakne.modes.ingestion import run_ingestion

        trace = run_ingestion(rec_id)

    assert trace.status == "completed"
    assert len(trace.touched_nodes) == 1
    assert trace.touched_nodes[0].action == "created"
    node_id = trace.touched_nodes[0].node_id

    # Node should exist in DB
    result = graph.query("MATCH (n:SemanticNode {id: $id}) RETURN n.id", {"id": node_id})
    assert result.result_set

    # Theme pass should have been triggered with the completion summary
    mock_theme.assert_called_once()
    assert mock_theme.call_args[0][0] == "Ingested a transcript about career anxiety."


def test_ingest_updates_existing_node(graph: Graph) -> None:
    """Agent calls update_node; log count increments."""
    rec_id = _store_transcript(graph)

    node_id = increment_counter(graph, "node")
    prov = ProvenanceInput(source_id=rec_id, start_offset=0, end_offset=10)
    store_graph.create_node(graph, ["career anxiety"], "Initial state.", "first entry", prov, node_id)

    prov2 = ProvenanceInput(source_id=rec_id, start_offset=14, end_offset=28)
    update_args = {
        "node_id": node_id,
        "note": "Mortgage fear now explicit.",
        "new_summary": "Career anxiety deepened by mortgage fear.",
        "provenance": prov2.model_dump(),
    }
    completion_args = {"summary": "Updated career anxiety node."}

    update_resp = _mock_response("update_node", update_args, "tc-1")
    done_resp = _mock_response("complete_ingestion", completion_args, "tc-2")

    with (
        patch("arakne.modes.ingestion.get_graph", return_value=graph),
        patch("arakne.modes.ingestion.theme_mode.run_theme_update"),
        patch("litellm.completion", side_effect=[update_resp, done_resp]),
        patch("arakne.modes.ingestion.save_trace"),
    ):
        from arakne.modes.ingestion import run_ingestion

        trace = run_ingestion(rec_id)

    assert trace.status == "completed"
    assert len(trace.touched_nodes) == 1
    assert trace.touched_nodes[0].action == "updated"

    # Log count should be 2 (1 create + 1 update)
    node_out = store_graph.get_node(graph, node_id)
    assert node_out.node.total_log_count == 2


def test_ingest_invalid_provenance_fails(graph: Graph) -> None:
    """Agent calls create_node without provenance; runner captures tool error and fails."""
    rec_id = _store_transcript(graph)

    bad_args = {
        "aliases": ["concept"],
        "summary": "Some concept.",
        "note": "No provenance.",
        # provenance omitted — will fail validation
    }
    bad_resp = _mock_response("create_node", bad_args)

    with (
        patch("arakne.modes.ingestion.get_graph", return_value=graph),
        patch("arakne.modes.ingestion.theme_mode.run_theme_update"),
        patch("litellm.completion", return_value=bad_resp),
        patch("arakne.modes.ingestion.save_trace"),
    ):
        from arakne.modes.ingestion import run_ingestion

        trace = run_ingestion(rec_id)

    assert trace.status == "failed"
    assert trace.touched_nodes == []


def test_ingest_no_writes_skips_theme(graph: Graph) -> None:
    """Agent calls complete_ingestion without any writes; theme mode is not triggered."""
    rec_id = _store_transcript(graph)

    done_resp = _mock_response("complete_ingestion", {"summary": "Nothing to change."})

    with (
        patch("arakne.modes.ingestion.get_graph", return_value=graph),
        patch("arakne.modes.ingestion.theme_mode.run_theme_update") as mock_theme,
        patch("litellm.completion", return_value=done_resp),
        patch("arakne.modes.ingestion.save_trace"),
    ):
        from arakne.modes.ingestion import run_ingestion

        trace = run_ingestion(rec_id)

    assert trace.status == "completed"
    assert trace.touched_nodes == []
    mock_theme.assert_not_called()


def test_ingest_missing_transcript_raises(graph: Graph) -> None:
    """run_ingestion raises ValueError for a non-existent transcript id."""
    with (
        patch("arakne.modes.ingestion.get_graph", return_value=graph),
        patch("arakne.modes.ingestion.save_trace"),
    ):
        from arakne.modes.ingestion import run_ingestion

        with pytest.raises(ValueError, match="not found"):
            run_ingestion("rec:999")


# ---------------------------------------------------------------------------
# run_theme_update
# ---------------------------------------------------------------------------


def test_theme_update_creates_theme(graph: Graph) -> None:
    """Theme agent calls create_theme then complete_theme_update; Theme node and priority_order persist."""
    rec_id = _store_transcript(graph)
    node_id = increment_counter(graph, "node")
    prov = ProvenanceInput(source_id=rec_id, start_offset=0, end_offset=10)
    store_graph.create_node(graph, ["job change"], "Career decision node.", "init", prov, node_id)

    create_theme_args = {
        "name": "career-direction",
        "state": "Weighing whether to leave job.",
        "anchors": [node_id],
        "status": ["active"],
    }
    completion_args = {
        "updated_themes": ["career-direction"],
        "priority_order": ["career-direction"],
    }

    create_resp = _mock_response("create_theme", create_theme_args, "tc-1")
    done_resp = _mock_response("complete_theme_update", completion_args, "tc-2")

    with (
        patch("arakne.modes.theme.get_graph", return_value=graph),
        patch("litellm.completion", side_effect=[create_resp, done_resp]),
        patch("arakne.modes.theme.save_trace"),
    ):
        from arakne.modes.theme import run_theme_update

        touched = [TouchedNode(node_id=node_id, action="created")]
        trace = run_theme_update("Career anxiety noted.", touched, [])

    assert trace.status == "completed"

    result = store_themes.get_theme(graph, "career-direction")
    assert result.theme.name == "career-direction"
    assert node_id in result.theme.anchors

    state = get_system(graph)
    assert state.theme_priority_order == ["career-direction"]


def test_theme_update_empty_map_runs(graph: Graph) -> None:
    """Theme agent can run with no existing themes."""
    completion_args = {"updated_themes": [], "priority_order": []}
    done_resp = _mock_response("complete_theme_update", completion_args)

    with (
        patch("arakne.modes.theme.get_graph", return_value=graph),
        patch("litellm.completion", return_value=done_resp),
        patch("arakne.modes.theme.save_trace"),
    ):
        from arakne.modes.theme import run_theme_update

        trace = run_theme_update("First session.", [], [])

    assert trace.status == "completed"


# ---------------------------------------------------------------------------
# Fence creation
# ---------------------------------------------------------------------------


def test_fence_not_created_below_budget(graph: Graph) -> None:
    """No fence when hot segment is within token budget."""
    node_id = increment_counter(graph, "node")
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    store_graph.create_node(graph, ["topic"], "A topic.", "initial entry", prov, node_id)

    store_graph.run_fence_checks(graph, [node_id], 10_000, settings.GEMINI_MODEL)

    node_out = store_graph.get_node(graph, node_id)
    assert not any(isinstance(e, FenceEntry) for e in node_out.node.log)


def test_fence_created_when_budget_exceeded(graph: Graph) -> None:
    """Fence is created when hot segment token count exceeds the budget."""
    node_id = increment_counter(graph, "node")
    prov0 = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    store_graph.create_node(
        graph, ["career"], "Career thoughts.", "initial note about career anxiety", prov0, node_id
    )
    for i in range(5):
        prov_i = ProvenanceInput(source_id="rec:1", start_offset=i * 10, end_offset=(i + 1) * 10)
        store_graph.update_node(
            graph, node_id,
            f"Update {i}: additional context about evolving career thoughts and emotional state",
            None, None, prov_i,
        )

    fence_resp = MagicMock()
    fence_resp.choices[0].message.content = "Career anxiety evolved from vague unease to concrete fear."

    with patch("litellm.completion", return_value=fence_resp):
        store_graph.run_fence_checks(graph, [node_id], 1, settings.GEMINI_MODEL)

    node_out = store_graph.get_node(graph, node_id)
    assert any(isinstance(e, FenceEntry) for e in node_out.node.log)


def test_fence_check_skips_deleted_node(graph: Graph) -> None:
    """run_fence_checks silently skips node_ids that no longer exist."""
    store_graph.run_fence_checks(graph, ["node:9999"], 1, settings.GEMINI_MODEL)
    # No exception raised
