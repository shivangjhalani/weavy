"""
Phase 1 tests — System node initialisation and counter minting.
Requires a running FalkorDB instance (provided by devenv up).
Uses the "arakne_test" graph to avoid touching the main graph.
"""

import pytest
from falkordb import Graph

from arakne.store.client import get_graph
from arakne.store.system import SystemState, get_system, increment_counter, init_system


TEST_GRAPH = "arakne_test"


@pytest.fixture
def graph() -> Graph:
    g = get_graph(TEST_GRAPH)
    # Clean state before each test
    g.query("MATCH (s:System) DELETE s")
    yield g
    # Clean up after
    g.query("MATCH (s:System) DELETE s")


def test_init_system_creates_node(graph: Graph) -> None:
    state = init_system(graph)

    assert isinstance(state, SystemState)
    assert state.next_node_id == 1
    assert state.next_edge_id == 1
    assert state.next_rec_id == 1
    assert state.next_chat_id == 1
    assert state.theme_priority_order == []
    assert state.log_token_budget > 0
    assert state.hot_theme_token_budget > 0


def test_init_system_idempotent(graph: Graph) -> None:
    state_a = init_system(graph)
    state_b = init_system(graph)

    assert state_a == state_b


def test_get_system_after_init(graph: Graph) -> None:
    init_system(graph)
    state = get_system(graph)

    assert state.next_node_id == 1
    assert state.theme_priority_order == []


def test_get_system_raises_if_missing(graph: Graph) -> None:
    # No init_system called — node does not exist
    with pytest.raises(RuntimeError, match="System node not found"):
        get_system(graph)


def test_increment_counter_node(graph: Graph) -> None:
    init_system(graph)

    token_a = increment_counter(graph, "node")
    token_b = increment_counter(graph, "node")

    assert token_a == "node:1"
    assert token_b == "node:2"


def test_increment_counter_all_types(graph: Graph) -> None:
    init_system(graph)

    assert increment_counter(graph, "node") == "node:1"
    assert increment_counter(graph, "edge") == "edge:1"
    assert increment_counter(graph, "rec") == "rec:1"
    assert increment_counter(graph, "chat") == "chat:1"

    # Second increment for each is independent
    assert increment_counter(graph, "node") == "node:2"
    assert increment_counter(graph, "rec") == "rec:2"


def test_increment_counter_raises_without_init(graph: Graph) -> None:
    with pytest.raises(RuntimeError, match="System node not found"):
        increment_counter(graph, "node")
