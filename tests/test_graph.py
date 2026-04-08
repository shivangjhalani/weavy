"""
Phase 3 tests — Semantic graph CRUD with provenance validation and log management.
Requires a running FalkorDB instance (provided by devenv up).
Uses the "weavy_test" graph to avoid touching the main graph.
"""

import json
from datetime import datetime, timezone

import pytest
from falkordb import Graph
from pydantic import ValidationError

from weavy.models.graph import LogEntry, ProvenanceInput
from weavy.models.tools import (
    CreateEdgeInput,
    CreateNodeInput,
    DeleteEdgeInput,
    DeleteNodeInput,
    GetNodeInput,
    SearchGraphInput,
    UpdateEdgeInput,
    UpdateNodeInput,
)
from weavy.models.traces import RunTrace
from weavy.services import memory
from weavy.store import graph as store_graph
from weavy.store.client import get_graph
from weavy.store.system import init_system

TEST_GRAPH = "weavy_test"


def _ingestion_trace() -> RunTrace:
    return RunTrace(
        mode="ingestion",
        started_at=datetime.now(tz=timezone.utc),
        input_summary="test",
    )


def _query_trace() -> RunTrace:
    return RunTrace(
        mode="query",
        started_at=datetime.now(tz=timezone.utc),
        input_summary="test",
    )


def _theme_trace() -> RunTrace:
    return RunTrace(
        mode="theme",
        started_at=datetime.now(tz=timezone.utc),
        input_summary="test",
    )


@pytest.fixture
def graph() -> Graph:
    g = get_graph(TEST_GRAPH)
    g.query("MATCH (s:System) DELETE s")
    g.query("MATCH (n:SemanticNode) DETACH DELETE n")
    init_system(g)
    return g


# ---------------------------------------------------------------------------
# create_node
# ---------------------------------------------------------------------------


def test_create_node_ingestion(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=30)
    params = CreateNodeInput(
        aliases=["career anxiety", "work stress"],
        summary="Persistent worry about career direction.",
        note="First mention in rec:1",
        provenance=prov,
    )
    result = memory.create_node(graph, params, _ingestion_trace())
    assert result.ok
    assert result.id is not None
    assert result.id.startswith("node:")

    # Verify the node exists in the store with the correct log entry
    out = store_graph.get_node(graph, result.id)
    assert out.node.aliases == ["career anxiety", "work stress"]
    assert out.node.summary == "Persistent worry about career direction."
    assert out.node.total_log_count == 1
    assert len(out.node.log) == 1
    entry = out.node.log[0]
    assert isinstance(entry, LogEntry)
    assert entry.source_id == "rec:1"
    assert entry.start_offset == 0
    assert entry.end_offset == 30
    assert entry.note == "First mention in rec:1"


def test_create_node_chat_provenance(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="chat:1", start_offset=3, end_offset=None)
    params = CreateNodeInput(
        aliases=["fear of failure"],
        summary="Fear of failing after a career change.",
        note="User mentioned during chat at message 3",
        provenance=prov,
    )
    result = memory.create_node(graph, params, _query_trace())
    assert result.ok
    assert result.id.startswith("node:")


def test_create_node_no_provenance_rejected(graph: Graph) -> None:
    params = CreateNodeInput(
        aliases=["something"],
        summary="Some concept.",
        note="no provenance",
        provenance=None,
    )
    with pytest.raises(ValueError, match="require provenance"):
        memory.create_node(graph, params, _ingestion_trace())


def test_create_node_wrong_source_rejected(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="chat:1", start_offset=0, end_offset=None)
    params = CreateNodeInput(
        aliases=["something"],
        summary="Some concept.",
        note="chat provenance in ingestion mode",
        provenance=prov,
    )
    with pytest.raises(ValueError, match="rec:"):
        memory.create_node(graph, params, _ingestion_trace())


def test_create_node_theme_mode_rejected(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    params = CreateNodeInput(
        aliases=["x"],
        summary="x",
        note="x",
        provenance=prov,
    )
    with pytest.raises(ValueError, match="Theme mode"):
        memory.create_node(graph, params, _theme_trace())


def test_create_node_recorded_in_trace(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    params = CreateNodeInput(
        aliases=["focus"],
        summary="Ability to focus deeply.",
        note="first mention",
        provenance=prov,
    )
    trace = _ingestion_trace()
    result = memory.create_node(graph, params, trace)
    assert len(trace.touched_nodes) == 1
    assert trace.touched_nodes[0].node_id == result.id
    assert trace.touched_nodes[0].action == "created"


# ---------------------------------------------------------------------------
# update_node
# ---------------------------------------------------------------------------


def test_update_node_archives_summary(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    node_id = memory.create_node(
        graph,
        CreateNodeInput(
            aliases=["anxiety"],
            summary="Original summary.",
            note="created",
            provenance=prov,
        ),
        _ingestion_trace(),
    ).id

    update_prov = ProvenanceInput(source_id="rec:2", start_offset=5, end_offset=15)
    memory.update_node(
        graph,
        UpdateNodeInput(
            node_id=node_id,
            note="Feeling resolved after therapy.",
            new_summary="Anxiety reduced significantly.",
            provenance=update_prov,
        ),
        _ingestion_trace(),
    )

    out = store_graph.get_node(graph, node_id)
    assert out.node.summary == "Anxiety reduced significantly."
    assert out.node.total_log_count == 2
    # Last log entry (hot, most recent) should contain archived summary
    hot_entry = out.node.log[-1]
    assert isinstance(hot_entry, LogEntry)
    assert "[archived summary] Original summary." in hot_entry.note
    assert "Feeling resolved after therapy." in hot_entry.note


def test_update_node_aliases_only(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    node_id = memory.create_node(
        graph,
        CreateNodeInput(
            aliases=["dad"],
            summary="Relationship with father.",
            note="created",
            provenance=prov,
        ),
        _ingestion_trace(),
    ).id

    update_prov = ProvenanceInput(source_id="rec:2", start_offset=0, end_offset=5)
    memory.update_node(
        graph,
        UpdateNodeInput(
            node_id=node_id,
            note="User now refers to him as 'papa'.",
            new_aliases=["dad", "papa", "father"],
            provenance=update_prov,
        ),
        _ingestion_trace(),
    )

    out = store_graph.get_node(graph, node_id)
    assert out.node.aliases == ["dad", "papa", "father"]
    assert out.node.summary == "Relationship with father."  # unchanged
    assert out.node.total_log_count == 2


def test_node_and_edge_ids_reject_trailing_punctuation() -> None:
    with pytest.raises(ValidationError, match=r"node:\d+"):
        UpdateNodeInput(
            node_id="node:4,",
            note="bad id",
            provenance=ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=1),
        )

    with pytest.raises(ValidationError, match=r"node:\d+"):
        CreateEdgeInput(from_node_id="node:1", to_node_id="node:2.", label="related")

    with pytest.raises(ValidationError, match=r"edge:\d+"):
        UpdateEdgeInput(edge_id="edge:3)", new_label="updated")


# ---------------------------------------------------------------------------
# delete_node
# ---------------------------------------------------------------------------


def test_delete_node_removes_node_and_edges(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    a = memory.create_node(
        graph,
        CreateNodeInput(aliases=["A"], summary="Node A", note="a", provenance=prov),
        _ingestion_trace(),
    ).id
    b = memory.create_node(
        graph,
        CreateNodeInput(aliases=["B"], summary="Node B", note="b", provenance=prov),
        _ingestion_trace(),
    ).id
    memory.create_edge(
        graph,
        CreateEdgeInput(from_node_id=a, to_node_id=b, label="related"),
        _ingestion_trace(),
    )

    trace = _ingestion_trace()
    memory.delete_node(graph, DeleteNodeInput(node_id=a, reason="test cleanup"), trace)
    assert trace.touched_nodes[-1].action == "deleted"

    # Node A gone
    with pytest.raises(ValueError):
        store_graph.get_node(graph, a)

    # Node B still exists, edge gone
    out_b = store_graph.get_node(graph, b)
    assert out_b.edges == []


def test_delete_node_not_found_raises(graph: Graph) -> None:
    with pytest.raises(ValueError):
        memory.delete_node(
            graph,
            DeleteNodeInput(node_id="node:9999", reason="missing"),
            _ingestion_trace(),
        )


# ---------------------------------------------------------------------------
# create_edge / update_edge / delete_edge
# ---------------------------------------------------------------------------


def test_create_edge(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    a = memory.create_node(
        graph,
        CreateNodeInput(aliases=["A"], summary="A", note="a", provenance=prov),
        _ingestion_trace(),
    ).id
    b = memory.create_node(
        graph,
        CreateNodeInput(aliases=["B"], summary="B", note="b", provenance=prov),
        _ingestion_trace(),
    ).id

    trace = _ingestion_trace()
    result = memory.create_edge(
        graph, CreateEdgeInput(from_node_id=a, to_node_id=b, label="causes"), trace
    )
    assert result.ok
    assert result.id.startswith("edge:")
    assert trace.touched_edges[0].action == "created"

    out = store_graph.get_node(graph, a)
    assert len(out.edges) == 1
    assert out.edges[0].label == "causes"


def test_update_edge_label(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    a = memory.create_node(
        graph,
        CreateNodeInput(aliases=["A"], summary="A", note="a", provenance=prov),
        _ingestion_trace(),
    ).id
    b = memory.create_node(
        graph,
        CreateNodeInput(aliases=["B"], summary="B", note="b", provenance=prov),
        _ingestion_trace(),
    ).id
    edge_id = memory.create_edge(
        graph,
        CreateEdgeInput(from_node_id=a, to_node_id=b, label="old label"),
        _ingestion_trace(),
    ).id

    memory.update_edge(
        graph,
        UpdateEdgeInput(edge_id=edge_id, new_label="new label"),
        _ingestion_trace(),
    )

    out = store_graph.get_node(graph, a)
    assert out.edges[0].label == "new label"


def test_delete_edge(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    a = memory.create_node(
        graph,
        CreateNodeInput(aliases=["A"], summary="A", note="a", provenance=prov),
        _ingestion_trace(),
    ).id
    b = memory.create_node(
        graph,
        CreateNodeInput(aliases=["B"], summary="B", note="b", provenance=prov),
        _ingestion_trace(),
    ).id
    edge_id = memory.create_edge(
        graph,
        CreateEdgeInput(from_node_id=a, to_node_id=b, label="linked"),
        _ingestion_trace(),
    ).id

    trace = _ingestion_trace()
    memory.delete_edge(graph, DeleteEdgeInput(edge_id=edge_id, reason="test"), trace)
    assert trace.touched_edges[-1].action == "deleted"

    # Both nodes remain, edge gone
    out_a = store_graph.get_node(graph, a)
    assert out_a.edges == []


# ---------------------------------------------------------------------------
# search_graph
# ---------------------------------------------------------------------------


def test_search_graph_alias_match(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    memory.create_node(
        graph,
        CreateNodeInput(
            aliases=["career anxiety", "work stress"],
            summary="Anxiety about career.",
            note="x",
            provenance=prov,
        ),
        _ingestion_trace(),
    )
    out = store_graph.search_graph(graph, SearchGraphInput(query="career"))
    assert len(out.results) >= 1
    assert any("career" in r.canonical_alias.lower() for r in out.results)


def test_search_graph_summary_match(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    memory.create_node(
        graph,
        CreateNodeInput(
            aliases=["meditation"],
            summary="Daily mindfulness practice helping anxiety.",
            note="x",
            provenance=prov,
        ),
        _ingestion_trace(),
    )
    out = store_graph.search_graph(graph, SearchGraphInput(query="mindfulness"))
    assert len(out.results) >= 1


def test_search_graph_no_match(graph: Graph) -> None:
    out = store_graph.search_graph(
        graph, SearchGraphInput(query="xyzzy_impossible_query_12345")
    )
    assert out.results == []


# ---------------------------------------------------------------------------
# get_node
# ---------------------------------------------------------------------------


def test_get_node_returns_edges(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    a = memory.create_node(
        graph,
        CreateNodeInput(aliases=["A"], summary="A", note="a", provenance=prov),
        _ingestion_trace(),
    ).id
    b = memory.create_node(
        graph,
        CreateNodeInput(aliases=["B"], summary="B", note="b", provenance=prov),
        _ingestion_trace(),
    ).id
    memory.create_edge(
        graph,
        CreateEdgeInput(from_node_id=a, to_node_id=b, label="test edge"),
        _ingestion_trace(),
    )

    out = memory.get_node(graph, GetNodeInput(node_ids=[a]))
    assert len(out.results[0].edges) == 1
    assert out.results[0].edges[0].label == "test edge"


def test_get_node_returns_multiple_results_and_not_found(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    a = memory.create_node(
        graph,
        CreateNodeInput(aliases=["A"], summary="A", note="a", provenance=prov),
        _ingestion_trace(),
    ).id
    b = memory.create_node(
        graph,
        CreateNodeInput(aliases=["B"], summary="B", note="b", provenance=prov),
        _ingestion_trace(),
    ).id

    out = memory.get_node(graph, GetNodeInput(node_ids=[a, "node:9999", b]))

    assert [result.node.id for result in out.results] == [a, b]
    assert out.not_found == ["node:9999"]


def test_get_node_json_has_iso_timestamps(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    node_id = memory.create_node(
        graph,
        CreateNodeInput(
            aliases=["test node"], summary="Test.", note="initial", provenance=prov
        ),
        _ingestion_trace(),
    ).id

    out = memory.get_node(graph, GetNodeInput(node_ids=[node_id]))
    payload = json.loads(out.model_dump_json())
    ts = payload["results"][0]["node"]["log"][0]["timestamp"]
    datetime.fromisoformat(ts)


# ---------------------------------------------------------------------------
# get_node_neighborhood
# ---------------------------------------------------------------------------


def test_get_node_neighborhood(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    a = memory.create_node(
        graph,
        CreateNodeInput(
            aliases=["career"],
            summary="Career direction concerns.",
            note="a",
            provenance=prov,
        ),
        _ingestion_trace(),
    ).id
    b = memory.create_node(
        graph,
        CreateNodeInput(
            aliases=["anxiety"],
            summary="Persistent anxiety.",
            note="b",
            provenance=prov,
        ),
        _ingestion_trace(),
    ).id
    c = memory.create_node(
        graph,
        CreateNodeInput(
            aliases=["mentor"],
            summary="Senior mentor at work.",
            note="c",
            provenance=prov,
        ),
        _ingestion_trace(),
    ).id
    memory.create_edge(
        graph,
        CreateEdgeInput(from_node_id=a, to_node_id=b, label="causes"),
        _ingestion_trace(),
    )
    memory.create_edge(
        graph,
        CreateEdgeInput(from_node_id=c, to_node_id=a, label="influences"),
        _ingestion_trace(),
    )

    out = store_graph.get_node_neighborhood(graph, a)
    assert out.node.id == a
    assert out.node.summary == "Career direction concerns."
    neighbor_ids = {n.node_id for n in out.neighbors}
    assert b in neighbor_ids
    assert c in neighbor_ids
