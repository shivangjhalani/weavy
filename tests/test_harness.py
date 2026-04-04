"""
Phase 4 tests — Agent harness: tracing, completion tools, registry, and runner loop.
Runner tests mock litellm.completion to avoid real LLM calls.
Integration tests that touch FalkorDB use the "arakne_test" graph.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from falkordb import Graph

from arakne.harness import registry as reg
from arakne.harness.registry import ToolContext, get_tool_definitions
from arakne.harness.runner import run
from arakne.harness.tracing import (
    finalize_trace,
    new_trace,
    record_tool_call,
    record_touched_edge,
    record_touched_node,
    save_trace,
)
from arakne.models.tools import (
    CompleteIngestionInput,
    CompleteThemeUpdateInput,
    CreateNodeInput,
    DeliverResponseInput,
)
from arakne.models.traces import RunTrace, ToolCall
from arakne.store.client import get_graph
from arakne.store.system import init_system
from arakne.tools.completion_tools import (
    complete_ingestion,
    complete_theme_update,
    deliver_response,
)

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
# tracing.py
# ---------------------------------------------------------------------------


def test_new_trace() -> None:
    trace = new_trace("ingestion", "first transcript")
    assert trace.mode == "ingestion"
    assert trace.input_summary == "first transcript"
    assert trace.status == "running"
    assert trace.started_at is not None
    assert trace.ended_at is None
    assert trace.tool_calls == []
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


def test_record_tool_call() -> None:
    trace = _running_trace()
    call = ToolCall(
        tool_name="search_graph",
        args={"query": "career"},
        result='{"results": []}',
        called_at=datetime.now(tz=timezone.utc),
    )
    record_tool_call(trace, call)
    assert len(trace.tool_calls) == 1
    assert trace.tool_calls[0].tool_name == "search_graph"


def test_record_touched_node() -> None:
    trace = _running_trace()
    record_touched_node(trace, "node:1", "created")
    assert len(trace.touched_nodes) == 1
    assert trace.touched_nodes[0].node_id == "node:1"
    assert trace.touched_nodes[0].action == "created"


def test_record_touched_edge() -> None:
    trace = _running_trace()
    record_touched_edge(trace, "edge:1", "deleted")
    assert len(trace.touched_edges) == 1
    assert trace.touched_edges[0].edge_id == "edge:1"
    assert trace.touched_edges[0].action == "deleted"


def test_save_trace() -> None:
    trace = _running_trace()
    finalize_trace(trace, "completed")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = save_trace(trace, tmpdir)
        assert os.path.exists(path)
        assert path.endswith(f"{trace.run_id}.json")
        with open(path) as f:
            data = json.load(f)
        assert data["run_id"] == trace.run_id
        assert data["status"] == "completed"


def test_save_trace_creates_directory() -> None:
    trace = _running_trace()
    finalize_trace(trace, "completed")
    with tempfile.TemporaryDirectory() as tmpdir:
        nested = os.path.join(tmpdir, "a", "b", "c")
        path = save_trace(trace, nested)
        assert os.path.exists(path)


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
# runner.py helpers
# ---------------------------------------------------------------------------


def _mock_response(tool_name: str, args: dict[str, Any], call_id: str = "tc-1") -> MagicMock:
    """Build a mock litellm.completion response for a single tool call."""
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


def _mock_no_tool_response() -> MagicMock:
    """Build a mock response where the model returns text without a tool call."""
    msg = MagicMock()
    msg.tool_calls = None
    msg.content = "I think the answer is..."

    choice = MagicMock()
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# runner.py — unit tests (no FalkorDB)
# ---------------------------------------------------------------------------


def test_run_fails_without_tool_call() -> None:
    with patch("litellm.completion", return_value=_mock_no_tool_response()):
        trace = run(
            mode="ingestion",
            system_prompt="You are an ingestion agent.",
            initial_messages=[{"role": "user", "content": "ingest rec:1"}],
            allowed_tools=reg.INGESTION_TOOLS,
            completion_tool="complete_ingestion",
            run_context={"input_summary": "rec:1"},
            graph=MagicMock(),
        )
    assert trace.status == "failed"
    assert "completion tool" in (trace.error or "")


def test_run_fails_on_unknown_tool() -> None:
    resp = _mock_response("nonexistent_tool", {})
    with patch("litellm.completion", return_value=resp):
        trace = run(
            mode="ingestion",
            system_prompt="You are an ingestion agent.",
            initial_messages=[],
            allowed_tools=reg.INGESTION_TOOLS,
            completion_tool="complete_ingestion",
            run_context={"input_summary": "test"},
            graph=MagicMock(),
        )
    assert trace.status == "failed"
    assert "Unknown tool" in (trace.error or "")
    assert trace.tool_calls[0].error is not None


def test_run_fails_on_bad_args() -> None:
    # search_graph requires a "query" field — pass garbage
    resp = _mock_response("search_graph", {"bad_field": 999})
    with patch("litellm.completion", return_value=resp):
        trace = run(
            mode="ingestion",
            system_prompt="You are an ingestion agent.",
            initial_messages=[],
            allowed_tools=reg.INGESTION_TOOLS,
            completion_tool="complete_ingestion",
            run_context={"input_summary": "test"},
            graph=MagicMock(),
        )
    assert trace.status == "failed"
    assert "Invalid arguments" in (trace.error or "")


def test_run_records_tool_calls() -> None:
    search_resp = _mock_response("search_graph", {"query": "career", "limit": 5}, "tc-1")
    completion_resp = _mock_response(
        "complete_ingestion", {"summary": "done"}, "tc-2"
    )

    # search_graph needs a real-ish graph mock — return a SearchGraphOutput-compatible object
    search_output = MagicMock()
    search_output.model_dump_json.return_value = '{"results":[]}'

    with (
        patch("litellm.completion", side_effect=[search_resp, completion_resp]),
        patch("arakne.tools.read_tools.search_graph", return_value=search_output),
    ):
        trace = run(
            mode="ingestion",
            system_prompt="You are an ingestion agent.",
            initial_messages=[],
            allowed_tools=reg.INGESTION_TOOLS,
            completion_tool="complete_ingestion",
            run_context={"input_summary": "test"},
            graph=MagicMock(),
        )

    assert trace.status == "completed"
    assert len(trace.tool_calls) == 2
    assert trace.tool_calls[0].tool_name == "search_graph"
    assert trace.tool_calls[1].tool_name == "complete_ingestion"


def test_run_completes_on_completion_tool() -> None:
    resp = _mock_response("complete_ingestion", {"summary": "all done"})
    with patch("litellm.completion", return_value=resp):
        trace = run(
            mode="ingestion",
            system_prompt="system",
            initial_messages=[],
            allowed_tools=reg.INGESTION_TOOLS,
            completion_tool="complete_ingestion",
            run_context={"input_summary": "test"},
            graph=MagicMock(),
        )
    assert trace.status == "completed"
    assert trace.completion_payload == {"summary": "all done"}
    assert trace.ended_at is not None


def test_run_fails_on_model_exception() -> None:
    with patch("litellm.completion", side_effect=RuntimeError("network error")):
        trace = run(
            mode="query",
            system_prompt="system",
            initial_messages=[],
            allowed_tools=reg.QUERY_TOOLS,
            completion_tool="deliver_response",
            run_context={"input_summary": "test"},
            graph=MagicMock(),
        )
    assert trace.status == "failed"
    assert "network error" in (trace.error or "")


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

    create_resp = _mock_response("create_node", create_args, "tc-1")
    completion_resp = _mock_response("complete_ingestion", completion_args, "tc-2")

    with patch("litellm.completion", side_effect=[create_resp, completion_resp]):
        trace = run(
            mode="ingestion",
            system_prompt="You are an ingestion agent.",
            initial_messages=[{"role": "user", "content": "ingest"}],
            allowed_tools=reg.INGESTION_TOOLS,
            completion_tool="complete_ingestion",
            run_context={"input_summary": "rec:1"},
            graph=graph,
        )

    assert trace.status == "completed"
    assert len(trace.touched_nodes) == 1
    assert trace.touched_nodes[0].action == "created"
    assert trace.touched_nodes[0].node_id.startswith("node:")
