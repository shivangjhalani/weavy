"""
Phase 5 + 6 tests — Ingestion flow, theme mode, and fence creation.
Mocks litellm.completion to avoid real LLM calls.
Uses the "weavy_test" graph to avoid touching the main graph.
"""

from unittest.mock import MagicMock, patch

import pytest
from falkordb import Graph

from weavy.config import settings
from weavy.models.graph import FenceEntry, ProvenanceInput
from weavy.models.traces import TouchedNode
from weavy.store import canonical as store_canonical
from weavy.store import graph as store_graph
from weavy.store import themes as store_themes
from weavy.store.rollback import rollback_ingestion
from weavy.store.system import get_system, increment_counter
from tests.helpers import mock_tool_response, reset_test_graph, store_test_transcript

SAMPLE_TRANSCRIPT = (
    "[0:00] I've been thinking about changing jobs a lot lately.\n"
    "[0:14] The mortgage scares me but I'm feeling trapped.\n"
    "[0:28] Had a great talk with my mentor yesterday about risk.\n"
)


@pytest.fixture
def graph() -> Graph:
    return reset_test_graph("Theme", "Transcript")
# ---------------------------------------------------------------------------
# run_ingestion
# ---------------------------------------------------------------------------


def test_ingest_into_empty_graph(graph: Graph) -> None:
    """Agent creates a node then calls complete_ingestion; node appears in graph."""
    rec_id = store_test_transcript(graph, SAMPLE_TRANSCRIPT)

    prov = ProvenanceInput(source_id=rec_id, start_offset=0, end_offset=14)
    create_args = {
        "aliases": ["job change"],
        "summary": "Contemplating leaving current job.",
        "note": "First mention — feels trapped, mortgage a barrier.",
        "provenance": prov.model_dump(),
    }
    completion_args = {"summary": "Ingested a transcript about career anxiety."}

    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    create_resp = mock_tool_response("create_node", create_args, "tc-1", usage=usage)
    done_resp = mock_tool_response("complete_ingestion", completion_args, "tc-2", usage=usage)

    with (
        patch("weavy.modes.ingestion.get_graph", return_value=graph),
        patch("weavy.modes.theme.run_theme_update") as mock_theme,
        patch("litellm.completion", side_effect=[create_resp, done_resp]),
    ):
        from weavy.modes.ingestion import run_ingestion

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
    rec_id = store_test_transcript(graph, SAMPLE_TRANSCRIPT)

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

    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    update_resp = mock_tool_response("update_node", update_args, "tc-1", usage=usage)
    done_resp = mock_tool_response("complete_ingestion", completion_args, "tc-2", usage=usage)

    with (
        patch("weavy.modes.ingestion.get_graph", return_value=graph),
        patch("weavy.modes.theme.run_theme_update"),
        patch("litellm.completion", side_effect=[update_resp, done_resp]),
    ):
        from weavy.modes.ingestion import run_ingestion

        trace = run_ingestion(rec_id)

    assert trace.status == "completed"
    assert len(trace.touched_nodes) == 1
    assert trace.touched_nodes[0].action == "updated"

    # Log count should be 2 (1 create + 1 update)
    node_out = store_graph.get_node(graph, node_id)
    assert node_out.node.total_log_count == 2


def test_ingest_invalid_provenance_fails(graph: Graph) -> None:
    """Agent calls create_node without provenance; runner captures tool error and fails."""
    rec_id = store_test_transcript(graph, SAMPLE_TRANSCRIPT)

    bad_args = {
        "aliases": ["concept"],
        "summary": "Some concept.",
        "note": "No provenance.",
        # provenance omitted — will fail validation
    }
    bad_resp = mock_tool_response(
        "create_node",
        bad_args,
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    )

    with (
        patch("weavy.modes.ingestion.get_graph", return_value=graph),
        patch("weavy.modes.theme.run_theme_update"),
        patch("litellm.completion", return_value=bad_resp),
    ):
        from weavy.modes.ingestion import run_ingestion

        trace = run_ingestion(rec_id)

    assert trace.status == "failed"
    assert trace.touched_nodes == []


def test_ingest_invalid_node_id_format_fails_at_argument_validation(graph: Graph) -> None:
    rec_id = store_test_transcript(graph, SAMPLE_TRANSCRIPT)

    bad_resp = mock_tool_response(
        "update_node",
        {
            "node_id": "node:4,",
            "note": "Malformed id copied from prose.",
            "provenance": ProvenanceInput(source_id=rec_id, start_offset=0, end_offset=14).model_dump(),
        },
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    )

    with (
        patch("weavy.modes.ingestion.get_graph", return_value=graph),
        patch("weavy.modes.theme.run_theme_update"),
        patch("litellm.completion", return_value=bad_resp),
    ):
        from weavy.modes.ingestion import run_ingestion

        trace = run_ingestion(rec_id)

    assert trace.status == "failed"
    assert trace.touched_nodes == []
    assert trace.error is not None
    assert "Invalid arguments for 'update_node'" in trace.error


def test_ingest_no_writes_skips_theme(graph: Graph) -> None:
    """Agent calls complete_ingestion without any writes; theme mode is not triggered."""
    rec_id = store_test_transcript(graph, SAMPLE_TRANSCRIPT)

    done_resp = mock_tool_response(
        "complete_ingestion",
        {"summary": "Nothing to change."},
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    )

    with (
        patch("weavy.modes.ingestion.get_graph", return_value=graph),
        patch("weavy.modes.theme.run_theme_update") as mock_theme,
        patch("litellm.completion", return_value=done_resp),
    ):
        from weavy.modes.ingestion import run_ingestion

        trace = run_ingestion(rec_id)

    assert trace.status == "completed"
    assert trace.touched_nodes == []
    mock_theme.assert_not_called()


def test_ingest_missing_transcript_raises(graph: Graph) -> None:
    """run_ingestion raises ValueError for a non-existent transcript id."""
    with patch("weavy.modes.ingestion.get_graph", return_value=graph):
        from weavy.modes.ingestion import run_ingestion

        with pytest.raises(ValueError, match="not found"):
            run_ingestion("rec:999")


def test_ingest_prompt_humanizes_recorded_timestamp(graph: Graph) -> None:
    rec_id = store_test_transcript(graph, SAMPLE_TRANSCRIPT)
    done_resp = mock_tool_response(
        "complete_ingestion",
        {"summary": "Nothing to change."},
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    )

    with (
        patch("weavy.modes.ingestion.get_graph", return_value=graph),
        patch("weavy.modes.theme.run_theme_update"),
        patch("litellm.completion", return_value=done_resp) as mock_completion,
    ):
        from weavy.modes.ingestion import run_ingestion

        run_ingestion(rec_id)

    sent_messages = mock_completion.call_args.kwargs["messages"]
    user_message = sent_messages[1]["content"]
    assert "Recorded: " in user_message
    assert "UTC" in user_message


# ---------------------------------------------------------------------------
# run_theme_update
# ---------------------------------------------------------------------------


def test_theme_update_creates_theme(graph: Graph) -> None:
    """Theme agent calls create_theme then complete_theme_update; Theme node and priority_order persist."""
    rec_id = store_test_transcript(graph, SAMPLE_TRANSCRIPT)
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

    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    create_resp = mock_tool_response("create_theme", create_theme_args, "tc-1", usage=usage)
    done_resp = mock_tool_response("complete_theme_update", completion_args, "tc-2", usage=usage)

    with (
        patch("weavy.modes.theme.get_graph", return_value=graph),
        patch("litellm.completion", side_effect=[create_resp, done_resp]),
    ):
        from weavy.modes.theme import run_theme_update

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
    done_resp = mock_tool_response(
        "complete_theme_update",
        completion_args,
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    )

    with (
        patch("weavy.modes.theme.get_graph", return_value=graph),
        patch("litellm.completion", return_value=done_resp),
    ):
        from weavy.modes.theme import run_theme_update

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


# ---------------------------------------------------------------------------
# Ingestion status flag
# ---------------------------------------------------------------------------


def test_ingestion_sets_flag(graph: Graph) -> None:
    """After a successful ingestion ingestion_status is 1."""
    rec_id = store_test_transcript(graph, SAMPLE_TRANSCRIPT)

    prov = ProvenanceInput(source_id=rec_id, start_offset=0, end_offset=14)
    create_args = {
        "aliases": ["job change"],
        "summary": "Contemplating leaving current job.",
        "note": "Feels trapped.",
        "provenance": prov.model_dump(),
    }
    completion_args = {"summary": "Ingested career transcript."}
    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

    with (
        patch("weavy.modes.ingestion.get_graph", return_value=graph),
        patch("weavy.modes.theme.run_theme_update"),
        patch("litellm.completion", side_effect=[
            mock_tool_response("create_node", create_args, "tc-1", usage=usage),
            mock_tool_response("complete_ingestion", completion_args, "tc-2", usage=usage),
        ]),
    ):
        from weavy.modes.ingestion import run_ingestion
        trace = run_ingestion(rec_id)

    assert trace.status == "completed"
    assert store_canonical.get_ingestion_status(graph, rec_id) == 1


def test_failed_ingestion_resets_flag(graph: Graph) -> None:
    """A failed run resets ingestion_status back to 0."""
    rec_id = store_test_transcript(graph, SAMPLE_TRANSCRIPT)

    bad_resp = mock_tool_response(
        "create_node",
        {"aliases": ["x"], "summary": "y", "note": "z"},  # missing provenance
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    )

    with (
        patch("weavy.modes.ingestion.get_graph", return_value=graph),
        patch("weavy.modes.theme.run_theme_update"),
        patch("litellm.completion", return_value=bad_resp),
    ):
        from weavy.modes.ingestion import run_ingestion
        trace = run_ingestion(rec_id)

    assert trace.status == "failed"
    assert store_canonical.get_ingestion_status(graph, rec_id) == 0


def test_reingest_blocked_when_flag_is_set(graph: Graph) -> None:
    """Second call to run_ingestion raises ValueError when flag is 1."""
    rec_id = store_test_transcript(graph, SAMPLE_TRANSCRIPT)
    store_canonical.set_ingestion_status(graph, rec_id, 1)
    store_canonical.save_run_manifest(graph, rec_id, [])

    with patch("weavy.modes.ingestion.get_graph", return_value=graph):
        from weavy.modes.ingestion import run_ingestion
        with pytest.raises(ValueError, match="already been ingested"):
            run_ingestion(rec_id)


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


def test_rollback_removes_created_node(graph: Graph) -> None:
    """After rollback, a node created during ingestion is deleted and flag is 0."""
    rec_id = store_test_transcript(graph, SAMPLE_TRANSCRIPT)

    prov = ProvenanceInput(source_id=rec_id, start_offset=0, end_offset=14)
    create_args = {
        "aliases": ["job change"],
        "summary": "Contemplating leaving current job.",
        "note": "Feels trapped.",
        "provenance": prov.model_dump(),
    }
    completion_args = {"summary": "Ingested."}
    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

    with (
        patch("weavy.modes.ingestion.get_graph", return_value=graph),
        patch("weavy.modes.theme.run_theme_update"),
        patch("litellm.completion", side_effect=[
            mock_tool_response("create_node", create_args, "tc-1", usage=usage),
            mock_tool_response("complete_ingestion", completion_args, "tc-2", usage=usage),
        ]),
    ):
        from weavy.modes.ingestion import run_ingestion
        trace = run_ingestion(rec_id)

    node_id = trace.touched_nodes[0].node_id

    with patch("weavy.store.rollback.get_graph", return_value=graph):
        rollback_ingestion(rec_id)

    # Node must be gone
    result = graph.query("MATCH (n:SemanticNode {id: $id}) RETURN n", {"id": node_id})
    assert not result.result_set

    # Flag reset, manifest cleared
    assert store_canonical.get_ingestion_status(graph, rec_id) == 0
    assert store_canonical.get_run_manifest(graph, rec_id) is None


def test_rollback_restores_updated_node(graph: Graph) -> None:
    """After rollback, an updated node reverts to its pre-ingestion state."""
    rec_id = store_test_transcript(graph, SAMPLE_TRANSCRIPT)

    # Create node with known initial state
    node_id = increment_counter(graph, "node")
    prov0 = ProvenanceInput(source_id=rec_id, start_offset=0, end_offset=10)
    store_graph.create_node(graph, ["career anxiety"], "Original summary.", "init", prov0, node_id)

    prov2 = ProvenanceInput(source_id=rec_id, start_offset=14, end_offset=28)
    update_args = {
        "node_id": node_id,
        "note": "Update during ingestion.",
        "new_summary": "Updated summary after ingestion.",
        "provenance": prov2.model_dump(),
    }
    completion_args = {"summary": "Updated node."}
    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

    with (
        patch("weavy.modes.ingestion.get_graph", return_value=graph),
        patch("weavy.modes.theme.run_theme_update"),
        patch("litellm.completion", side_effect=[
            mock_tool_response("update_node", update_args, "tc-1", usage=usage),
            mock_tool_response("complete_ingestion", completion_args, "tc-2", usage=usage),
        ]),
    ):
        from weavy.modes.ingestion import run_ingestion
        run_ingestion(rec_id)

    # Confirm node was updated
    node_out = store_graph.get_node(graph, node_id)
    assert node_out.node.summary == "Updated summary after ingestion."

    with patch("weavy.store.rollback.get_graph", return_value=graph):
        rollback_ingestion(rec_id)

    # Node must be back to original state
    node_out = store_graph.get_node(graph, node_id)
    assert node_out.node.summary == "Original summary."
    assert node_out.node.total_log_count == 1

    assert store_canonical.get_ingestion_status(graph, rec_id) == 0


def test_reingest_allowed_after_rollback(graph: Graph) -> None:
    """run_ingestion succeeds again after rollback resets the flag."""
    rec_id = store_test_transcript(graph, SAMPLE_TRANSCRIPT)

    completion_args = {"summary": "Nothing to change."}
    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    done_resp = mock_tool_response("complete_ingestion", completion_args, usage=usage)

    with (
        patch("weavy.modes.ingestion.get_graph", return_value=graph),
        patch("weavy.modes.theme.run_theme_update"),
        patch("litellm.completion", return_value=done_resp),
    ):
        from weavy.modes.ingestion import run_ingestion
        run_ingestion(rec_id)

    with patch("weavy.store.rollback.get_graph", return_value=graph):
        rollback_ingestion(rec_id)

    assert store_canonical.get_ingestion_status(graph, rec_id) == 0

    with (
        patch("weavy.modes.ingestion.get_graph", return_value=graph),
        patch("weavy.modes.theme.run_theme_update"),
        patch("litellm.completion", return_value=done_resp),
    ):
        trace2 = run_ingestion(rec_id)

    assert trace2.status == "completed"


def test_rollback_no_manifest_resets_flag(graph: Graph) -> None:
    """rollback_ingestion with no manifest (failed run) still resets the flag to 0."""
    rec_id = store_test_transcript(graph, SAMPLE_TRANSCRIPT)
    # Simulate a stuck flag from a run that failed before saving the manifest.
    store_canonical.set_ingestion_status(graph, rec_id, 1)

    with patch("weavy.store.rollback.get_graph", return_value=graph):
        rollback_ingestion(rec_id)  # must not raise

    assert store_canonical.get_ingestion_status(graph, rec_id) == 0
