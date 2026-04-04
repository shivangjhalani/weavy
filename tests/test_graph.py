"""
Phase 3 tests — Semantic graph CRUD with provenance validation and log management.
Requires a running FalkorDB instance (provided by devenv up).
Uses the "arakne_test" graph to avoid touching the main graph.
"""

import json
from datetime import datetime, timezone

import pytest
from falkordb import Graph

from arakne.models.graph import FenceEntry, LogEntry, ProvenanceInput
from arakne.models.tools import (
    CreateEdgeInput,
    CreateNodeInput,
    DeleteEdgeInput,
    DeleteNodeInput,
    GetColdLogsInput,
    GetNodeInput,
    GetNodeNeighborhoodInput,
    SearchGraphInput,
    UpdateEdgeInput,
    UpdateNodeInput,
)
from arakne.models.traces import RunTrace
from arakne.store import graph as store_graph
from arakne.store.client import get_graph
from arakne.store.system import increment_counter, init_system
from arakne.tools import write_tools

TEST_GRAPH = "arakne_test"


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
    result = write_tools.create_node(graph, params, _ingestion_trace())
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
    result = write_tools.create_node(graph, params, _query_trace())
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
        write_tools.create_node(graph, params, _ingestion_trace())


def test_create_node_wrong_source_rejected(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="chat:1", start_offset=0, end_offset=None)
    params = CreateNodeInput(
        aliases=["something"],
        summary="Some concept.",
        note="chat provenance in ingestion mode",
        provenance=prov,
    )
    with pytest.raises(ValueError, match="rec:"):
        write_tools.create_node(graph, params, _ingestion_trace())


def test_create_node_theme_mode_rejected(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    params = CreateNodeInput(
        aliases=["x"],
        summary="x",
        note="x",
        provenance=prov,
    )
    with pytest.raises(ValueError, match="Theme mode"):
        write_tools.create_node(graph, params, _theme_trace())


def test_create_node_recorded_in_trace(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    params = CreateNodeInput(
        aliases=["focus"],
        summary="Ability to focus deeply.",
        note="first mention",
        provenance=prov,
    )
    trace = _ingestion_trace()
    result = write_tools.create_node(graph, params, trace)
    assert len(trace.touched_nodes) == 1
    assert trace.touched_nodes[0].node_id == result.id
    assert trace.touched_nodes[0].action == "created"


# ---------------------------------------------------------------------------
# update_node
# ---------------------------------------------------------------------------


def test_update_node_archives_summary(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    node_id = write_tools.create_node(
        graph,
        CreateNodeInput(aliases=["anxiety"], summary="Original summary.", note="created", provenance=prov),
        _ingestion_trace(),
    ).id

    update_prov = ProvenanceInput(source_id="rec:2", start_offset=5, end_offset=15)
    write_tools.update_node(
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
    node_id = write_tools.create_node(
        graph,
        CreateNodeInput(aliases=["dad"], summary="Relationship with father.", note="created", provenance=prov),
        _ingestion_trace(),
    ).id

    update_prov = ProvenanceInput(source_id="rec:2", start_offset=0, end_offset=5)
    write_tools.update_node(
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


def test_update_node_increments_log_count(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    node_id = write_tools.create_node(
        graph,
        CreateNodeInput(aliases=["x"], summary="x", note="x", provenance=prov),
        _ingestion_trace(),
    ).id
    for i in range(3):
        p = ProvenanceInput(source_id=f"rec:{i + 2}", start_offset=0, end_offset=5)
        write_tools.update_node(
            graph,
            UpdateNodeInput(node_id=node_id, note=f"update {i}", provenance=p),
            _ingestion_trace(),
        )
    out = store_graph.get_node(graph, node_id)
    assert out.node.total_log_count == 4


# ---------------------------------------------------------------------------
# delete_node
# ---------------------------------------------------------------------------


def test_delete_node_removes_node_and_edges(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    a = write_tools.create_node(
        graph,
        CreateNodeInput(aliases=["A"], summary="Node A", note="a", provenance=prov),
        _ingestion_trace(),
    ).id
    b = write_tools.create_node(
        graph,
        CreateNodeInput(aliases=["B"], summary="Node B", note="b", provenance=prov),
        _ingestion_trace(),
    ).id
    write_tools.create_edge(graph, CreateEdgeInput(from_node_id=a, to_node_id=b, label="related"), _ingestion_trace())

    trace = _ingestion_trace()
    write_tools.delete_node(graph, DeleteNodeInput(node_id=a, reason="test cleanup"), trace)
    assert trace.touched_nodes[-1].action == "deleted"

    # Node A gone
    with pytest.raises(ValueError):
        store_graph.get_node(graph, a)

    # Node B still exists, edge gone
    out_b = store_graph.get_node(graph, b)
    assert out_b.edges == []


def test_delete_node_not_found_raises(graph: Graph) -> None:
    with pytest.raises(ValueError):
        write_tools.delete_node(graph, DeleteNodeInput(node_id="node:9999", reason="missing"), _ingestion_trace())


# ---------------------------------------------------------------------------
# create_edge / update_edge / delete_edge
# ---------------------------------------------------------------------------


def test_create_edge(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    a = write_tools.create_node(
        graph, CreateNodeInput(aliases=["A"], summary="A", note="a", provenance=prov), _ingestion_trace()
    ).id
    b = write_tools.create_node(
        graph, CreateNodeInput(aliases=["B"], summary="B", note="b", provenance=prov), _ingestion_trace()
    ).id

    trace = _ingestion_trace()
    result = write_tools.create_edge(graph, CreateEdgeInput(from_node_id=a, to_node_id=b, label="causes"), trace)
    assert result.ok
    assert result.id.startswith("edge:")
    assert trace.touched_edges[0].action == "created"

    out = store_graph.get_node(graph, a)
    assert len(out.edges) == 1
    assert out.edges[0].label == "causes"


def test_update_edge_label(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    a = write_tools.create_node(
        graph, CreateNodeInput(aliases=["A"], summary="A", note="a", provenance=prov), _ingestion_trace()
    ).id
    b = write_tools.create_node(
        graph, CreateNodeInput(aliases=["B"], summary="B", note="b", provenance=prov), _ingestion_trace()
    ).id
    edge_id = write_tools.create_edge(
        graph, CreateEdgeInput(from_node_id=a, to_node_id=b, label="old label"), _ingestion_trace()
    ).id

    write_tools.update_edge(graph, UpdateEdgeInput(edge_id=edge_id, new_label="new label"), _ingestion_trace())

    out = store_graph.get_node(graph, a)
    assert out.edges[0].label == "new label"


def test_delete_edge(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    a = write_tools.create_node(
        graph, CreateNodeInput(aliases=["A"], summary="A", note="a", provenance=prov), _ingestion_trace()
    ).id
    b = write_tools.create_node(
        graph, CreateNodeInput(aliases=["B"], summary="B", note="b", provenance=prov), _ingestion_trace()
    ).id
    edge_id = write_tools.create_edge(
        graph, CreateEdgeInput(from_node_id=a, to_node_id=b, label="linked"), _ingestion_trace()
    ).id

    trace = _ingestion_trace()
    write_tools.delete_edge(graph, DeleteEdgeInput(edge_id=edge_id, reason="test"), trace)
    assert trace.touched_edges[-1].action == "deleted"

    # Both nodes remain, edge gone
    out_a = store_graph.get_node(graph, a)
    assert out_a.edges == []


# ---------------------------------------------------------------------------
# search_graph
# ---------------------------------------------------------------------------


def test_search_graph_alias_match(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    write_tools.create_node(
        graph,
        CreateNodeInput(aliases=["career anxiety", "work stress"], summary="Anxiety about career.", note="x", provenance=prov),
        _ingestion_trace(),
    )
    from arakne.tools.read_tools import search_graph as read_search
    out = read_search(graph, SearchGraphInput(query="career"))
    assert len(out.results) >= 1
    assert any("career" in r.canonical_alias.lower() for r in out.results)


def test_search_graph_summary_match(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    write_tools.create_node(
        graph,
        CreateNodeInput(aliases=["meditation"], summary="Daily mindfulness practice helping anxiety.", note="x", provenance=prov),
        _ingestion_trace(),
    )
    from arakne.tools.read_tools import search_graph as read_search
    out = read_search(graph, SearchGraphInput(query="mindfulness"))
    assert len(out.results) >= 1


def test_search_graph_no_match(graph: Graph) -> None:
    from arakne.tools.read_tools import search_graph as read_search
    out = read_search(graph, SearchGraphInput(query="xyzzy_impossible_query_12345"))
    assert out.results == []


# ---------------------------------------------------------------------------
# get_node
# ---------------------------------------------------------------------------


def test_get_node_returns_edges(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    a = write_tools.create_node(
        graph, CreateNodeInput(aliases=["A"], summary="A", note="a", provenance=prov), _ingestion_trace()
    ).id
    b = write_tools.create_node(
        graph, CreateNodeInput(aliases=["B"], summary="B", note="b", provenance=prov), _ingestion_trace()
    ).id
    write_tools.create_edge(graph, CreateEdgeInput(from_node_id=a, to_node_id=b, label="test edge"), _ingestion_trace())

    from arakne.tools.read_tools import get_node as read_get_node
    out = read_get_node(graph, GetNodeInput(node_ids=[a]))
    assert len(out.results[0].edges) == 1
    assert out.results[0].edges[0].label == "test edge"
    assert out.results[0].cold_hint is None  # no fence yet


def test_get_node_hot_cold_split(graph: Graph) -> None:
    """After injecting a fence entry, get_node should set cold_hint."""
    from datetime import timezone
    from arakne.models.graph import FenceEntry
    from arakne.store import graph as sg

    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    node_id = write_tools.create_node(
        graph, CreateNodeInput(aliases=["test node"], summary="Test.", note="initial", provenance=prov), _ingestion_trace()
    ).id

    # Add a second log entry
    p2 = ProvenanceInput(source_id="rec:2", start_offset=0, end_offset=5)
    write_tools.update_node(graph, UpdateNodeInput(node_id=node_id, note="update", provenance=p2), _ingestion_trace())

    # Manually inject a fence entry into the log (simulating Phase 8 fence creation)
    fence = FenceEntry(
        is_fence=True,
        timestamp=datetime.now(tz=timezone.utc),
        note="Fence summarizing 2 entries.",
        entries_behind=2,
        date_range=(datetime.now(tz=timezone.utc), datetime.now(tz=timezone.utc)),
    )
    fence_json = sg._serialize_log_entry(fence)
    graph.query(
        "MATCH (n:SemanticNode {id: $id}) SET n.log = n.log + [$fence_json]",
        {"id": node_id, "fence_json": fence_json},
    )

    # Add a hot entry after the fence
    p3 = ProvenanceInput(source_id="rec:3", start_offset=0, end_offset=5)
    write_tools.update_node(graph, UpdateNodeInput(node_id=node_id, note="hot update", provenance=p3), _ingestion_trace())

    from arakne.tools.read_tools import get_node as read_get_node
    out = read_get_node(graph, GetNodeInput(node_ids=[node_id]))
    # Returned log should be [fence, hot_entry]
    assert len(out.results[0].node.log) == 2
    assert isinstance(out.results[0].node.log[0], FenceEntry)
    assert isinstance(out.results[0].node.log[1], LogEntry)
    assert out.results[0].cold_hint is not None
    assert "get_cold_logs" in out.results[0].cold_hint


def test_get_node_json_humanizes_log_timestamps(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    node_id = write_tools.create_node(
        graph, CreateNodeInput(aliases=["test node"], summary="Test.", note="initial", provenance=prov), _ingestion_trace()
    ).id

    from arakne.tools.read_tools import get_node as read_get_node

    out = read_get_node(graph, GetNodeInput(node_ids=[node_id]))
    payload = json.loads(out.model_dump_json())
    assert "UTC" in payload["results"][0]["node"]["log"][0]["timestamp"]


def test_get_cold_logs_json_humanizes_fence_dates(graph: Graph) -> None:
    fence = FenceEntry(
        is_fence=True,
        timestamp=datetime.now(tz=timezone.utc),
        note="Fence summarizing entries.",
        entries_behind=2,
        date_range=(datetime.now(tz=timezone.utc), datetime.now(tz=timezone.utc)),
    )
    node_id = increment_counter(graph, "node")
    store_graph.create_node(
        graph,
        ["test node"],
        "Test.",
        "initial",
        ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10),
        node_id,
    )
    graph.query(
        "MATCH (n:SemanticNode {id: $id}) SET n.log = n.log + [$fence_json]",
        {"id": node_id, "fence_json": store_graph._serialize_log_entry(fence)},
    )

    from arakne.tools.read_tools import get_cold_logs as read_get_cold_logs

    out = read_get_cold_logs(graph, GetColdLogsInput(node_id=node_id))
    payload = json.loads(out.model_dump_json())
    assert "UTC" in payload["entries"][-1]["timestamp"]
    assert all("UTC" in item for item in payload["entries"][-1]["date_range"])


# ---------------------------------------------------------------------------
# get_node_neighborhood
# ---------------------------------------------------------------------------


def test_get_node_neighborhood(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    a = write_tools.create_node(
        graph, CreateNodeInput(aliases=["career"], summary="Career direction concerns.", note="a", provenance=prov), _ingestion_trace()
    ).id
    b = write_tools.create_node(
        graph, CreateNodeInput(aliases=["anxiety"], summary="Persistent anxiety.", note="b", provenance=prov), _ingestion_trace()
    ).id
    c = write_tools.create_node(
        graph, CreateNodeInput(aliases=["mentor"], summary="Senior mentor at work.", note="c", provenance=prov), _ingestion_trace()
    ).id
    write_tools.create_edge(graph, CreateEdgeInput(from_node_id=a, to_node_id=b, label="causes"), _ingestion_trace())
    write_tools.create_edge(graph, CreateEdgeInput(from_node_id=c, to_node_id=a, label="influences"), _ingestion_trace())

    from arakne.tools.read_tools import get_node_neighborhood as read_neighborhood
    out = read_neighborhood(graph, GetNodeNeighborhoodInput(node_id=a))
    assert out.node.id == a
    assert out.node.summary == "Career direction concerns."
    neighbor_ids = {n.node_id for n in out.neighbors}
    assert b in neighbor_ids
    assert c in neighbor_ids


# ---------------------------------------------------------------------------
# get_cold_logs
# ---------------------------------------------------------------------------


def test_get_cold_logs_empty_for_new_node(graph: Graph) -> None:
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    node_id = write_tools.create_node(
        graph, CreateNodeInput(aliases=["fresh"], summary="Fresh node.", note="x", provenance=prov), _ingestion_trace()
    ).id

    from arakne.tools.read_tools import get_cold_logs as read_cold
    out = read_cold(graph, GetColdLogsInput(node_id=node_id))
    assert out.entries == []
