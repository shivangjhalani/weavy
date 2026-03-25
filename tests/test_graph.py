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
        type="person",
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
    assert result["type"] == "person"
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
        type="concept",
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
        type="topic",
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
        type="person",
        summary="Bob is a physicist.",
        aliases=["Bob"],
    )
    node_b = Node(
        id="test-edge-node-b",
        type="concept",
        summary="Quantum mechanics is Bob's main research area.",
        aliases=["QM"],
    )

    create_node(graph, node_a)
    create_node(graph, node_b)

    edge = Edge(
        id="test-edge-001",
        type="studies",
        source_id="test-edge-node-a",
        target_id="test-edge-node-b",
        summary="Bob studies quantum mechanics as his primary research topic.",
    )

    create_edge(graph, edge)

    # Verify edge exists by querying it directly
    result = graph.query(
        "MATCH ()-[r:EDGE {id: $id}]->() RETURN r.id, r.type, r.summary",
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
        type="person",
        summary="Carol is a data scientist.",
        aliases=["Carol"],
    )
    node_d = Node(
        id="test-edge-node-d",
        type="concept",
        summary="Deep learning is Carol's specialty.",
        aliases=["DL"],
    )

    create_node(graph, node_c)
    create_node(graph, node_d)

    edge = Edge(
        id="test-edge-002",
        type="works_on",
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
# Test 8: vector_search returns (id, summary, score) tuples
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_vector_search_return_format(graph):
    """vector_search returns list of (node_id, summary, score) tuples."""
    from lifeos.memory.graph import vector_search

    results = vector_search(graph, "software engineering", k=5)
    assert isinstance(results, list)
    if results:
        first = results[0]
        assert len(first) == 3
        assert isinstance(first[0], str)  # node_id
        assert isinstance(first[1], str)  # summary
        assert isinstance(first[2], float)  # score
