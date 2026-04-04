"""
Phase 4 tests — Agent harness: tracing, completion tools, registry, and runner loop.
Runner tests mock litellm.completion to avoid real LLM calls.
Integration tests that touch FalkorDB use the "arakne_test" graph.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from falkordb import Graph

from arakne.harness import registry as reg
from arakne.harness import runner as harness_runner
from arakne.harness.registry import get_tool_definitions
from arakne.harness.runner import run
from arakne.harness.tracing import (
    RunTracer,
    finalize_trace,
    new_trace,
    record_turn,
)
from arakne.modes._common import run_post_trace_hooks
from arakne.models.tools import (
    CompleteIngestionInput,
    CompleteThemeUpdateInput,
    DeliverResponseInput,
)
from arakne.models.traces import RunTrace, ToolCall, TouchedEdge, TouchedNode, Turn, TurnUsage
from arakne.store.client import get_graph
from arakne.store.system import SystemState, init_system
from arakne.tools.completion_tools import (
    complete_ingestion,
    complete_theme_update,
    deliver_response,
)
from tests.conftest import mock_tool_response

TEST_GRAPH = "arakne_test"


def _running_trace(mode: str = "ingestion") -> RunTrace:
    return RunTrace(
        mode=mode,  # type: ignore[arg-type]
        started_at=datetime.now(tz=timezone.utc),
        input_summary="test run",
        status="running",
    )


@pytest.fixture
def graph() -> Graph:
    g = get_graph(TEST_GRAPH)
    g.query("MATCH (s:System) DELETE s")
    g.query("MATCH (n:SemanticNode) DETACH DELETE n")
    init_system(g)
    return g


# ---------------------------------------------------------------------------
# tracing.py — in-memory RunTrace helpers
# ---------------------------------------------------------------------------


def test_new_trace() -> None:
    trace = new_trace("ingestion", "first transcript")
    assert trace.mode == "ingestion"
    assert trace.input_summary == "first transcript"
    assert trace.status == "running"
    assert trace.started_at is not None
    assert trace.ended_at is None
    assert trace.turns == []
    assert trace.touched_nodes == []
    assert trace.touched_edges == []


def test_finalize_trace_completed() -> None:
    trace = _running_trace()
    payload = {"summary": "done"}
    finalize_trace(trace, "completed", completion_payload=payload)
    assert trace.status == "completed"
    assert trace.ended_at is not None
    assert trace.completion_payload == payload
    assert trace.error is None


def test_finalize_trace_failed() -> None:
    trace = _running_trace()
    finalize_trace(trace, "failed", error="something went wrong")
    assert trace.status == "failed"
    assert trace.ended_at is not None
    assert trace.error == "something went wrong"


def test_run_post_trace_hooks_deduplicates_live_nodes() -> None:
    trace = _running_trace("query")
    trace.status = "completed"
    trace.touched_nodes = [
        TouchedNode(node_id="node:1", action="updated"),
        TouchedNode(node_id="node:1", action="updated"),
        TouchedNode(node_id="node:2", action="deleted"),
        TouchedNode(node_id="node:3", action="created"),
    ]
    trace.completion_payload = {"answer": "done"}
    system_state = SystemState(
        next_node_id=1,
        next_edge_id=1,
        next_rec_id=1,
        next_chat_id=1,
        theme_priority_order=[],
        log_token_budget=200,
        hot_theme_token_budget=100,
    )

    with (
        patch("arakne.modes._common.store_graph.run_fence_checks") as mock_fence_checks,
        patch("arakne.modes.theme.run_theme_update") as mock_theme_update,
    ):
        run_post_trace_hooks(trace, MagicMock(), system_state, "done")

    mock_fence_checks.assert_called_once()
    assert mock_fence_checks.call_args.args[1] == ["node:1", "node:3"]
    mock_theme_update.assert_called_once_with("done", trace.touched_nodes, trace.touched_edges)


def test_record_turn() -> None:
    trace = _running_trace()
    call = ToolCall(
        tool_name="search_graph",
        args={"query": "career"},
        result='{"results": []}',
        called_at=datetime.now(tz=timezone.utc),
    )
    turn = Turn(
        turn_number=1,
        tool_calls=[call],
        usage=TurnUsage(prompt_tokens=100, completion_tokens=50, reasoning_tokens=10, total_tokens=160),
        timestamp=datetime.now(tz=timezone.utc),
    )
    record_turn(trace, turn)
    assert len(trace.turns) == 1
    assert trace.turns[0].tool_calls[0].tool_name == "search_graph"
    assert trace.total_usage.prompt_tokens == 100
    assert trace.total_usage.total_tokens == 160


def test_touched_node_tracking() -> None:
    trace = _running_trace()
    trace.touched_nodes.append(TouchedNode(node_id="node:1", action="created"))
    assert len(trace.touched_nodes) == 1
    assert trace.touched_nodes[0].node_id == "node:1"
    assert trace.touched_nodes[0].action == "created"


def test_touched_edge_tracking() -> None:
    trace = _running_trace()
    trace.touched_edges.append(TouchedEdge(edge_id="edge:1", action="deleted"))
    assert len(trace.touched_edges) == 1
    assert trace.touched_edges[0].edge_id == "edge:1"
    assert trace.touched_edges[0].action == "deleted"


# ---------------------------------------------------------------------------
# tracing.py — RunTracer (mocked Langfuse)
# ---------------------------------------------------------------------------


def _make_tracer(mode: str = "ingestion") -> tuple[RunTracer, MagicMock]:
    """Create a RunTracer with a mocked Langfuse client. Returns (tracer, mock_langfuse)."""
    mock_lf = MagicMock()
    mock_root = MagicMock()
    mock_lf.start_observation.return_value = mock_root

    with patch("arakne.langfuse_client.langfuse", mock_lf):
        tracer = RunTracer("test-run-id", mode, "test input")

    tracer._lf = mock_lf
    tracer._root = mock_root
    return tracer, mock_lf


def test_run_tracer_creates_langfuse_trace() -> None:
    mock_lf = MagicMock()
    mock_root = MagicMock()
    mock_lf.start_observation.return_value = mock_root

    with patch("arakne.langfuse_client.langfuse", mock_lf):
        tracer = RunTracer("run-123", "ingestion", "Ingesting rec:1", session_id="rec:1")

    mock_lf.start_observation.assert_called_once()
    call_kwargs = mock_lf.start_observation.call_args[1]
    assert call_kwargs["trace_context"] == {"trace_id": "run-123"}
    assert call_kwargs["name"] == "ingestion-run"
    assert call_kwargs["input"] == "Ingesting rec:1"
    assert tracer.get_trace_id() == "run-123"


def test_run_tracer_start_and_end_turn() -> None:
    tracer, _ = _make_tracer()
    mock_turn_span = MagicMock()
    tracer._root.start_observation.return_value = mock_turn_span

    tracer.start_turn(1, 5)
    assert tracer._current_turn_span is mock_turn_span
    call_kwargs = tracer._root.start_observation.call_args[1]
    assert call_kwargs["name"] == "turn-1"
    assert call_kwargs["input"] == {"message_count": 5}

    tracer.end_turn("some text")
    mock_turn_span.update.assert_called_with(output="some text")
    mock_turn_span.end.assert_called_once()
    assert tracer._current_turn_span is None


def test_run_tracer_record_tool_call() -> None:
    tracer, _ = _make_tracer()
    mock_turn_span = MagicMock()
    mock_tool_span = MagicMock()
    tracer._root.start_observation.return_value = mock_turn_span
    mock_turn_span.start_observation.return_value = mock_tool_span

    tracer.start_turn(1, 3)
    tracer.record_tool_call(1, "tc-1", "search_graph", {"query": "career"}, '{"results":[]}', 42.0)

    mock_turn_span.start_observation.assert_called_once()
    call_kwargs = mock_turn_span.start_observation.call_args[1]
    assert call_kwargs["name"] == "tool:search_graph"
    assert call_kwargs["input"] == {"query": "career"}
    assert call_kwargs["as_type"] == "tool"
    mock_tool_span.update.assert_called_once_with(output='{"results":[]}')
    mock_tool_span.end.assert_called_once()


def test_run_tracer_record_tool_error() -> None:
    tracer, _ = _make_tracer()
    mock_turn_span = MagicMock()
    mock_tool_span = MagicMock()
    tracer._root.start_observation.return_value = mock_turn_span
    mock_turn_span.start_observation.return_value = mock_tool_span

    tracer.start_turn(1, 2)
    tracer.record_tool_error(1, "tc-1", "create_node", {}, "Invalid provenance")

    call_kwargs = mock_turn_span.start_observation.call_args[1]
    assert call_kwargs["level"] == "ERROR"
    assert call_kwargs["status_message"] == "Invalid provenance"
    mock_tool_span.end.assert_called_once()


def test_run_tracer_finalize_flushes() -> None:
    tracer, mock_lf = _make_tracer()
    usage = TurnUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

    tracer.finalize("completed", 2, usage, {"summary": "done"}, [], [])

    tracer._root.set_trace_io.assert_called_once_with(output={"summary": "done"})
    tracer._root.update.assert_called_once()
    update_kwargs = tracer._root.update.call_args[1]
    assert update_kwargs["metadata"]["status"] == "completed"
    tracer._root.end.assert_called_once()
    mock_lf.flush.assert_called_once()


# ---------------------------------------------------------------------------
# completion_tools.py
# ---------------------------------------------------------------------------


def test_complete_ingestion() -> None:
    trace = _running_trace("ingestion")
    params = CompleteIngestionInput(summary="ingested 3 nodes from rec:1")
    result = complete_ingestion(params, trace)
    assert result.ok is True
    assert trace.completion_payload == {"summary": "ingested 3 nodes from rec:1"}


def test_deliver_response() -> None:
    trace = _running_trace("query")
    params = DeliverResponseInput(
        answer="The answer is 42.",
        cited_sources=[],
        consulted_nodes=["node:1"],
    )
    result = deliver_response(params, trace)
    assert result.ok is True
    assert trace.completion_payload["answer"] == "The answer is 42."
    assert trace.completion_payload["consulted_nodes"] == ["node:1"]


def test_complete_theme_update() -> None:
    trace = _running_trace("theme")
    params = CompleteThemeUpdateInput(
        updated_themes=["career"],
        priority_order=["career", "health"],
    )
    result = complete_theme_update(params, trace)
    assert result.ok is True
    assert trace.completion_payload["priority_order"] == ["career", "health"]


# ---------------------------------------------------------------------------
# registry.py
# ---------------------------------------------------------------------------


def test_registry_contains_all_expected_tools() -> None:
    expected = {
        "search_graph", "get_node", "get_node_neighborhood", "get_cold_logs",
        "list_transcripts", "get_transcript_span", "list_chats", "get_chat",
        "get_theme", "create_node", "update_node", "delete_node",
        "create_edge", "update_edge", "delete_edge",
        "create_theme", "update_theme", "retire_theme",
        "complete_ingestion", "deliver_response", "complete_theme_update",
    }
    assert expected == set(reg.REGISTRY.keys())


def test_get_tool_definitions_format() -> None:
    defs = get_tool_definitions(["search_graph", "complete_ingestion"])
    assert len(defs) == 2
    for d in defs:
        assert d["type"] == "function"
        assert "name" in d["function"]
        assert "description" in d["function"]
        assert "parameters" in d["function"]


def test_ingestion_tools_include_completion() -> None:
    assert "complete_ingestion" in reg.INGESTION_TOOLS
    assert "deliver_response" not in reg.INGESTION_TOOLS


def test_completion_entries_marked() -> None:
    assert reg.REGISTRY["complete_ingestion"].is_completion is True
    assert reg.REGISTRY["deliver_response"].is_completion is True
    assert reg.REGISTRY["complete_theme_update"].is_completion is True
    assert reg.REGISTRY["create_node"].is_completion is False


def test_write_entries_marked_as_mutation() -> None:
    for name in ["create_node", "update_node", "delete_node", "create_edge"]:
        assert reg.REGISTRY[name].is_mutation is True
    for name in ["search_graph", "get_node"]:
        assert reg.REGISTRY[name].is_mutation is False


# ---------------------------------------------------------------------------
# runner.py — unit tests (no FalkorDB)
# ---------------------------------------------------------------------------
def _mock_no_tool_response() -> MagicMock:
    """Build a mock response where the model returns text without a tool call."""
    msg = MagicMock()
    msg.tool_calls = None
    msg.content = "I think the answer is..."
    msg.reasoning_content = None

    choice = MagicMock()
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = None
    return resp


def _mock_run_tracer() -> MagicMock:
    """Mock RunTracer to avoid real Langfuse calls in runner unit tests."""
    mock = MagicMock(spec=RunTracer)
    mock.get_trace_id.return_value = "mock-trace-id"
    return mock


def test_run_fails_without_tool_call() -> None:
    with (
        patch("litellm.completion", return_value=_mock_no_tool_response()),
        patch("arakne.harness.runner.RunTracer", return_value=_mock_run_tracer()),
    ):
        trace = run(
            mode="ingestion",
            system_prompt="You are an ingestion agent.",
            initial_messages=[{"role": "user", "content": "ingest rec:1"}],
            allowed_tools=reg.INGESTION_TOOLS,
            run_context={"input_summary": "rec:1"},
            graph=MagicMock(),
        )
    assert trace.status == "failed"
    assert "Model stopped without calling a completion tool." in (trace.error or "")


def test_run_fails_on_unknown_tool() -> None:
    resp = mock_tool_response("nonexistent_tool", {})
    with (
        patch("litellm.completion", return_value=resp),
        patch("arakne.harness.runner.RunTracer", return_value=_mock_run_tracer()),
    ):
        trace = run(
            mode="ingestion",
            system_prompt="You are an ingestion agent.",
            initial_messages=[],
            allowed_tools=reg.INGESTION_TOOLS,
            run_context={"input_summary": "test"},
            graph=MagicMock(),
        )
    assert trace.status == "failed"
    assert "Unknown tool" in (trace.error or "")
    assert trace.turns[0].tool_calls[0].error is not None


def test_run_fails_on_bad_args() -> None:
    resp = mock_tool_response("search_graph", {"bad_field": 999})
    with (
        patch("litellm.completion", return_value=resp),
        patch("arakne.harness.runner.RunTracer", return_value=_mock_run_tracer()),
    ):
        trace = run(
            mode="ingestion",
            system_prompt="You are an ingestion agent.",
            initial_messages=[],
            allowed_tools=reg.INGESTION_TOOLS,
            run_context={"input_summary": "test"},
            graph=MagicMock(),
        )
    assert trace.status == "failed"
    assert "Invalid arguments for 'search_graph'" in (trace.error or "")


def test_run_records_tool_calls() -> None:
    search_resp = mock_tool_response("search_graph", {"query": "career", "limit": 5}, "tc-1")
    completion_resp = mock_tool_response("complete_ingestion", {"summary": "done"}, "tc-2")

    search_output = MagicMock()
    search_output.model_dump_json.return_value = '{"results":[]}'

    with (
        patch("litellm.completion", side_effect=[search_resp, completion_resp]),
        patch("arakne.tools.read_tools.search_graph", return_value=search_output),
        patch("arakne.harness.runner.RunTracer", return_value=_mock_run_tracer()),
    ):
        trace = run(
            mode="ingestion",
            system_prompt="You are an ingestion agent.",
            initial_messages=[],
            allowed_tools=reg.INGESTION_TOOLS,
            run_context={"input_summary": "test"},
            graph=MagicMock(),
        )

    assert trace.status == "completed"
    assert len(trace.turns) == 2
    assert trace.turns[0].tool_calls[0].tool_name == "search_graph"
    assert trace.turns[1].tool_calls[0].tool_name == "complete_ingestion"


def test_run_completes_on_completion_tool() -> None:
    resp = mock_tool_response("complete_ingestion", {"summary": "all done"})
    with (
        patch("litellm.completion", return_value=resp),
        patch("arakne.harness.runner.RunTracer", return_value=_mock_run_tracer()),
    ):
        trace = run(
            mode="ingestion",
            system_prompt="system",
            initial_messages=[],
            allowed_tools=reg.INGESTION_TOOLS,
            run_context={"input_summary": "test"},
            graph=MagicMock(),
        )
    assert trace.status == "completed"
    assert trace.completion_payload == {"summary": "all done"}
    assert trace.ended_at is not None


def test_run_fails_on_model_exception() -> None:
    with (
        patch("litellm.completion", side_effect=RuntimeError("network error")),
        patch("arakne.harness.runner.RunTracer", return_value=_mock_run_tracer()),
    ):
        trace = run(
            mode="query",
            system_prompt="system",
            initial_messages=[],
            allowed_tools=reg.QUERY_TOOLS,
            run_context={"input_summary": "test"},
            graph=MagicMock(),
        )
    assert trace.status == "failed"
    assert "network error" in (trace.error or "")


def test_run_caches_context_limit_lookup() -> None:
    harness_runner._get_context_limit.cache_clear()
    resp = mock_tool_response("complete_ingestion", {"summary": "all done"})

    with (
        patch("litellm.get_model_info", return_value={"max_input_tokens": 123}) as mock_info,
        patch("litellm.completion", return_value=resp),
        patch("arakne.harness.runner.RunTracer", return_value=_mock_run_tracer()),
    ):
        for _ in range(2):
            trace = run(
                mode="ingestion",
                system_prompt="system",
                initial_messages=[],
                allowed_tools=reg.INGESTION_TOOLS,
                run_context={"input_summary": "test"},
                graph=MagicMock(),
            )
            assert trace.status == "completed"

    assert mock_info.call_count == 1
    harness_runner._get_context_limit.cache_clear()


# ---------------------------------------------------------------------------
# runner.py — integration test (uses FalkorDB)
# ---------------------------------------------------------------------------


def test_run_with_graph_write_records_touched_nodes(graph: Graph) -> None:
    """Runner executes a create_node call and the trace captures the touched node."""
    from arakne.models.graph import ProvenanceInput

    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=30)
    create_args = {
        "aliases": ["test concept"],
        "summary": "A test concept node.",
        "note": "created during harness test",
        "provenance": prov.model_dump(),
    }
    completion_args = {"summary": "done"}

    create_resp = mock_tool_response("create_node", create_args, "tc-1")
    completion_resp = mock_tool_response("complete_ingestion", completion_args, "tc-2")

    with (
        patch("litellm.completion", side_effect=[create_resp, completion_resp]),
        patch("arakne.harness.runner.RunTracer", return_value=_mock_run_tracer()),
    ):
        trace = run(
            mode="ingestion",
            system_prompt="You are an ingestion agent.",
            initial_messages=[{"role": "user", "content": "ingest"}],
            allowed_tools=reg.INGESTION_TOOLS,
            run_context={"input_summary": "rec:1"},
            graph=graph,
        )

    assert trace.status == "completed"
    assert len(trace.touched_nodes) == 1
    assert trace.touched_nodes[0].action == "created"
    assert trace.touched_nodes[0].node_id.startswith("node:")
