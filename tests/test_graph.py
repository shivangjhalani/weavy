"""Integration tests for lifeos/memory/graph.py.

These tests require:
  - FalkorDB running (devenv up)
  - GEMINI_API_KEY set in .env
Mark: @pytest.mark.integration
"""

import uuid
from datetime import datetime, timezone

import pytest

from lifeos.memory.models import Edge, LogEntry, Node, TranscriptRef


@pytest.fixture(scope="module")
def test_graph_name():
    """Generate a unique temporary graph name for this test run."""
    return f"test_lifeos_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def graph(test_graph_name):
    """Create a temporary graph, yield it, then drop it."""
    from lifeos.memory.graph import init_graph

    g = init_graph(graph_name=test_graph_name)
    yield g
    # Cleanup: delete all nodes and relationships
    try:
        g.query("MATCH (n) DETACH DELETE n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Test 1: init_graph connects and creates indexes without errors
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_init_graph(graph):
    """init_graph() should succeed — creates range + vector indexes."""
    assert graph is not None


# ---------------------------------------------------------------------------
# Test 2: init_graph is idempotent
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_init_graph_idempotent(test_graph_name):
    """Calling init_graph twice must not raise any errors."""
    from lifeos.memory.graph import init_graph

    g1 = init_graph(graph_name=test_graph_name)
    g2 = init_graph(graph_name=test_graph_name)
    assert g1 is not None
    assert g2 is not None


# ---------------------------------------------------------------------------
# Test 3: create_node and get_node
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_create_and_get_node(graph):
    """create_node stores a node; get_node retrieves it with correct fields."""
    from lifeos.memory.graph import create_node, get_node

    node = Node(
        id="test-node-001",
        name="Alice",
        summary="Alice is a software engineer who loves distributed systems.",
        aliases=["Alice", "alice@example.com"],
        log=[
            LogEntry(
                recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                note="First mention",
            )
        ],
        refs=[
            TranscriptRef(
                transcript_id="t-001",
                start_offset=10,
                end_offset=50,
            )
        ],
    )

    create_node(graph, node)

    result = get_node(graph, "test-node-001")
    assert result is not None
    assert result["id"] == "test-node-001"
    assert result["name"] == "Alice"
    assert "Alice" in result["summary"]


# ---------------------------------------------------------------------------
# Test 4: update_node re-embeds atomically
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_update_node_reembeds(graph):
    """update_node changes summary AND updates embedding atomically."""
    from lifeos.memory.graph import create_node, get_node, update_node

    node = Node(
        id="test-node-002",
        name="ML Concept",
        summary="Machine learning is a subset of artificial intelligence.",
        aliases=["ML"],
    )

    create_node(graph, node)

    # Capture the original embedding
    before = get_node(graph, "test-node-002")
    assert before is not None
    original_embedding = before.get("embedding")

    # Update with a very different summary
    update_node(
        graph,
        node_id="test-node-002",
        new_summary="Quantum physics studies the behavior of matter at subatomic scales.",
        log_entry="Updated to cover quantum physics.",
    )

    after = get_node(graph, "test-node-002")
    assert after is not None
    assert "quantum" in after["summary"].lower()
    # Embedding must have changed
    new_embedding = after.get("embedding")
    assert new_embedding is not None
    assert new_embedding != original_embedding


# ---------------------------------------------------------------------------
# Test 5: vector_search finds the updated node
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_vector_search_finds_updated(graph):
    """After update_node, vector_search for the new text returns that node."""
    from lifeos.memory.graph import create_node, update_node, vector_search

    node = Node(
        id="test-node-003",
        name="Pasta Topic",
        summary="Cooking pasta requires boiling water and adding salt.",
        aliases=["pasta cooking"],
    )

    create_node(graph, node)

    update_node(
        graph,
        node_id="test-node-003",
        new_summary="Quantum entanglement is a phenomenon in quantum mechanics.",
        log_entry="Updated to quantum entanglement.",
    )

    results = vector_search(graph, "quantum entanglement", k=10)
    assert len(results) > 0

    # The updated node must appear in the results
    node_ids = [r[0] for r in results]
    assert "test-node-003" in node_ids


# ---------------------------------------------------------------------------
# Test 6: create_edge stores edge retrievable by id
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_create_edge(graph):
    """create_edge stores an edge between two nodes."""
    from lifeos.memory.graph import create_edge, create_node

    node_a = Node(
        id="test-edge-node-a",
        name="Bob",
        summary="Bob is a physicist.",
        aliases=["Bob"],
    )
    node_b = Node(
        id="test-edge-node-b",
        name="Quantum Mechanics",
        summary="Quantum mechanics is Bob's main research area.",
        aliases=["QM"],
    )

    create_node(graph, node_a)
    create_node(graph, node_b)

    edge = Edge(
        id="test-edge-001",
        label="studies",
        source_id="test-edge-node-a",
        target_id="test-edge-node-b",
        summary="Bob studies quantum mechanics as his primary research topic.",
    )

    create_edge(graph, edge)

    # Verify edge exists by querying it directly
    result = graph.query(
        "MATCH ()-[r:EDGE {id: $id}]->() RETURN r.id, r.label, r.summary",
        {"id": "test-edge-001"},
    )
    rows = result.result_set
    assert len(rows) > 0
    assert rows[0][0] == "test-edge-001"
    assert rows[0][1] == "studies"


# ---------------------------------------------------------------------------
# Test 7: update_edge re-embeds atomically
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_update_edge_reembeds(graph):
    """update_edge changes summary AND embedding in the same operation."""
    from lifeos.memory.graph import create_edge, create_node, update_edge

    node_c = Node(
        id="test-edge-node-c",
        name="Carol",
        summary="Carol is a data scientist.",
        aliases=["Carol"],
    )
    node_d = Node(
        id="test-edge-node-d",
        name="Deep Learning",
        summary="Deep learning is Carol's specialty.",
        aliases=["DL"],
    )

    create_node(graph, node_c)
    create_node(graph, node_d)

    edge = Edge(
        id="test-edge-002",
        label="works_on",
        source_id="test-edge-node-c",
        target_id="test-edge-node-d",
        summary="Carol works on deep learning model architectures.",
    )

    create_edge(graph, edge)

    # Get original edge embedding
    before = graph.query(
        "MATCH ()-[r:EDGE {id: $id}]->() RETURN r.embedding",
        {"id": "test-edge-002"},
    )
    original_embedding = before.result_set[0][0] if before.result_set else None

    update_edge(
        graph,
        edge_id="test-edge-002",
        new_summary="Carol pivoted to studying classical music theory.",
        log_entry="Major career change noted.",
    )

    after = graph.query(
        "MATCH ()-[r:EDGE {id: $id}]->() RETURN r.summary, r.embedding",
        {"id": "test-edge-002"},
    )
    assert after.result_set
    new_summary = after.result_set[0][0]
    new_embedding = after.result_set[0][1]
    assert "music" in new_summary.lower() or "carol" in new_summary.lower()
    assert new_embedding is not None
    assert new_embedding != original_embedding


# ---------------------------------------------------------------------------
# Test 8: vector_search returns (node_id, name, aliases, summary, score) tuples
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_vector_search_return_format(graph):
    """vector_search returns list of (node_id, name, aliases, summary, score) 5-tuples."""
    from lifeos.memory.graph import vector_search

    results = vector_search(graph, "software engineering", k=5)
    assert isinstance(results, list)
    if results:
        first = results[0]
        assert len(first) == 5
        assert isinstance(first[0], str)   # node_id
        assert isinstance(first[1], str)   # name
        # aliases is a list (may be empty list)
        assert isinstance(first[2], (list, type(None)))  # aliases
        assert isinstance(first[3], str)   # summary
        assert isinstance(first[4], float)  # score


# ---------------------------------------------------------------------------
# Test 9: delete_node removes the node from the graph
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_delete_node(graph):
    """create_node then delete_node: get_node returns None after deletion."""
    from lifeos.memory.graph import create_node, delete_node, get_node

    node = Node(
        id="test-delete-node-001",
        name="TempNode",
        summary="This node will be deleted.",
    )
    create_node(graph, node)

    # Confirm it exists
    assert get_node(graph, "test-delete-node-001") is not None

    # Delete it
    delete_node(graph, "test-delete-node-001")

    # Confirm it's gone
    assert get_node(graph, "test-delete-node-001") is None


# ---------------------------------------------------------------------------
# Test 10: delete_edge removes the edge but leaves nodes intact
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_delete_edge(graph):
    """create_edge then delete_edge: edge gone, both nodes still exist."""
    from lifeos.memory.graph import create_edge, create_node, delete_edge, get_node

    node_x = Node(
        id="test-delete-edge-node-x",
        name="NodeX",
        summary="Source node for edge deletion test.",
    )
    node_y = Node(
        id="test-delete-edge-node-y",
        name="NodeY",
        summary="Target node for edge deletion test.",
    )
    create_node(graph, node_x)
    create_node(graph, node_y)

    edge = Edge(
        id="test-delete-edge-001",
        label="connected_to",
        source_id="test-delete-edge-node-x",
        target_id="test-delete-edge-node-y",
        summary="X connects to Y.",
    )
    create_edge(graph, edge)

    # Confirm edge exists
    result = graph.query(
        "MATCH ()-[r:EDGE {id: $id}]->() RETURN r.id",
        {"id": "test-delete-edge-001"},
    )
    assert len(result.result_set) > 0

    # Delete the edge
    delete_edge(graph, "test-delete-edge-001")

    # Confirm edge is gone
    result = graph.query(
        "MATCH ()-[r:EDGE {id: $id}]->() RETURN r.id",
        {"id": "test-delete-edge-001"},
    )
    assert len(result.result_set) == 0

    # Confirm nodes still exist
    assert get_node(graph, "test-delete-edge-node-x") is not None
    assert get_node(graph, "test-delete-edge-node-y") is not None


# ---------------------------------------------------------------------------
# Test 11: search_nodes_by_alias finds nodes by alias membership
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_search_nodes_by_alias(graph):
    """search_nodes_by_alias returns nodes whose aliases list contains the given alias."""
    from lifeos.memory.graph import create_node, search_nodes_by_alias

    node = Node(
        id="test-alias-node-001",
        name="Alice Full Name",
        summary="Alice is a person with multiple aliases.",
        aliases=["Alice", "Ali", "al@example.com"],
    )
    create_node(graph, node)

    # Search by middle alias
    results = search_nodes_by_alias(graph, "Ali")
    node_ids = [r["id"] for r in results]
    assert "test-alias-node-001" in node_ids

    # Result must include name and summary
    match = next(r for r in results if r["id"] == "test-alias-node-001")
    assert match["name"] == "Alice Full Name"
    assert "Alice" in match["summary"]


# ---------------------------------------------------------------------------
# Test 12: set_node_log replaces log without touching summary/embedding
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_set_node_log(graph):
    """set_node_log replaces the log entries without changing summary or embedding."""
    from lifeos.memory.graph import create_node, get_node, set_node_log

    node = Node(
        id="test-set-log-node-001",
        name="LogNode",
        summary="A node used to test set_node_log.",
    )
    create_node(graph, node)

    before = get_node(graph, "test-set-log-node-001")
    original_summary = before["summary"]

    # Set a new log
    new_entries = [
        {"recorded_at": "2026-01-01T00:00:00+00:00", "note": "Compressed entry A"},
        {"recorded_at": "2026-01-02T00:00:00+00:00", "note": "Compressed entry B"},
    ]
    set_node_log(graph, "test-set-log-node-001", new_entries)

    after = get_node(graph, "test-set-log-node-001")
    # Summary must be unchanged
    assert after["summary"] == original_summary
    # Log must be updated
    import json
    stored_log = json.loads(after["log"])
    assert len(stored_log) == 2
    assert stored_log[0]["note"] == "Compressed entry A"


# ---------------------------------------------------------------------------
# Test 13: update_node with new_aliases merges without duplicates
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_update_node_with_new_aliases(graph):
    """update_node with new_aliases=["Ali"] extends aliases to include both."""
    from lifeos.memory.graph import create_node, get_node, update_node

    node = Node(
        id="test-alias-update-node-001",
        name="AliasTest",
        summary="Testing alias extension.",
        aliases=["Alice"],
    )
    create_node(graph, node)

    update_node(
        graph,
        node_id="test-alias-update-node-001",
        new_summary="Testing alias extension — updated.",
        log_entry="Updated aliases.",
        new_aliases=["Ali"],
    )

    after = get_node(graph, "test-alias-update-node-001")
    stored_aliases = after["aliases"]
    assert "Alice" in stored_aliases
    assert "Ali" in stored_aliases


# ---------------------------------------------------------------------------
# Test 14: get_node_edges returns correct shape
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_get_node_edges_returns_correct_shape(graph):
    """get_node_edges returns edges with edge_id, label, summary, source, target, direction."""
    from lifeos.memory.graph import create_edge, create_node, get_node_edges

    node_p = Node(
        id="test-edges-node-p",
        name="PersonP",
        summary="Person P for edge traversal test.",
        aliases=["PersonP"],
    )
    node_q = Node(
        id="test-edges-node-q",
        name="PersonQ",
        summary="Person Q for edge traversal test.",
        aliases=["PersonQ"],
    )
    create_node(graph, node_p)
    create_node(graph, node_q)

    edge = Edge(
        id="test-traversal-edge-001",
        label="mentors",
        source_id="test-edges-node-p",
        target_id="test-edges-node-q",
        summary="PersonP mentors PersonQ.",
    )
    create_edge(graph, edge)

    # get edges from P's perspective — should be outgoing
    edges = get_node_edges(graph, "test-edges-node-p")
    assert isinstance(edges, list)
    assert len(edges) >= 1

    match = next((e for e in edges if e["edge_id"] == "test-traversal-edge-001"), None)
    assert match is not None, "Expected edge not found in results"
    assert match["label"] == "mentors"
    assert match["direction"] == "outgoing"
    assert match["source"]["id"] == "test-edges-node-p"
    assert match["source"]["name"] == "PersonP"
    assert match["target"]["id"] == "test-edges-node-q"
    assert match["target"]["name"] == "PersonQ"

    # get edges from Q's perspective — should be incoming
    edges_q = get_node_edges(graph, "test-edges-node-q")
    match_q = next((e for e in edges_q if e["edge_id"] == "test-traversal-edge-001"), None)
    assert match_q is not None
    assert match_q["direction"] == "incoming"


# ---------------------------------------------------------------------------
# Test 15: get_edge returns full edge state with parsed log
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_get_edge_returns_full_state(graph):
    """get_edge returns edge dict with log parsed from JSON and no embedding field."""
    from lifeos.memory.graph import create_edge, create_node, get_edge

    node_r = Node(
        id="test-get-edge-node-r",
        name="NodeR",
        summary="Source node for get_edge test.",
    )
    node_s = Node(
        id="test-get-edge-node-s",
        name="NodeS",
        summary="Target node for get_edge test.",
    )
    create_node(graph, node_r)
    create_node(graph, node_s)

    edge = Edge(
        id="test-get-edge-001",
        label="collaborates_with",
        source_id="test-get-edge-node-r",
        target_id="test-get-edge-node-s",
        summary="R and S collaborate on projects.",
        log=[LogEntry(recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc), note="First noted")],
    )
    create_edge(graph, edge)

    result = get_edge(graph, "test-get-edge-001")
    assert result is not None
    assert result["edge_id"] == "test-get-edge-001"
    assert result["label"] == "collaborates_with"
    assert result["source_id"] == "test-get-edge-node-r"
    assert result["target_id"] == "test-get-edge-node-s"
    # log must be a parsed list, not a JSON string
    assert isinstance(result["log"], list)
    assert len(result["log"]) == 1
    assert result["log"][0]["note"] == "First noted"
    # refs must be a parsed list
    assert isinstance(result["refs"], list)
    # embedding must NOT be present
    assert "embedding" not in result


@pytest.mark.integration
def test_get_edge_returns_none_for_missing(graph):
    """get_edge returns None when no edge with the given id exists."""
    from lifeos.memory.graph import get_edge

    result = get_edge(graph, "nonexistent-edge-id-xyz")
    assert result is None
