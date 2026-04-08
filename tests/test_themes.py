"""
Phase 6 tests — Theme CRUD, anchor management, and hot-theme rendering.
Requires a running FalkorDB instance (provided by devenv up).
Uses the "weavy_test" graph to avoid touching the main graph.
"""

import pytest
from falkordb import Graph

from weavy.models.graph import ProvenanceInput
from weavy.models.themes import Theme
from weavy.store import themes as store_themes
from weavy.store.client import get_graph
from weavy.store.graph import create_node
from weavy.store.system import increment_counter, init_system

TEST_GRAPH = "weavy_test"


@pytest.fixture
def graph() -> Graph:
    g = get_graph(TEST_GRAPH)
    g.query("MATCH (s:System) DELETE s")
    g.query("MATCH (n:SemanticNode) DETACH DELETE n")
    g.query("MATCH (t:Theme) DETACH DELETE t")
    init_system(g)
    return g


def _make_node(graph: Graph, name: str) -> str:
    """Create a SemanticNode and return its id."""
    node_id = increment_counter(graph, "node")
    prov = ProvenanceInput(source_id="rec:1", start_offset=0, end_offset=10)
    create_node(graph, [name], f"Summary of {name}", "test note", prov, node_id)
    return node_id


# ---------------------------------------------------------------------------
# create_theme / get_theme
# ---------------------------------------------------------------------------


def test_create_theme_basic(graph: Graph) -> None:
    node_id = _make_node(graph, "career")
    store_themes.create_theme(
        graph, "career-direction", "Weighing a job change.", [node_id], ["active"]
    )
    result = store_themes.get_theme(graph, "career-direction")
    theme = result.theme
    assert theme.name == "career-direction"
    assert theme.state == "Weighing a job change."
    assert theme.status == ["active"]
    assert node_id in theme.anchors


def test_create_theme_no_anchors(graph: Graph) -> None:
    store_themes.create_theme(
        graph, "sleep-routine", "Tracking sleep.", [], ["emerging"]
    )
    result = store_themes.get_theme(graph, "sleep-routine")
    assert result.theme.anchors == []


def test_create_theme_invalid_anchor(graph: Graph) -> None:
    with pytest.raises(ValueError, match="not found as SemanticNode"):
        store_themes.create_theme(graph, "bad-theme", "state", ["node:999"], ["active"])


def test_get_theme_not_found(graph: Graph) -> None:
    with pytest.raises(ValueError, match="not found"):
        store_themes.get_theme(graph, "nonexistent")


# ---------------------------------------------------------------------------
# update_theme
# ---------------------------------------------------------------------------


def test_update_theme_state_only(graph: Graph) -> None:
    node_id = _make_node(graph, "meditation")
    store_themes.create_theme(
        graph, "meditation-practice", "Just started.", [node_id], ["emerging"]
    )
    store_themes.update_theme(
        graph,
        "meditation-practice",
        new_state="Practiced for 2 weeks.",
        new_anchors=None,
        new_status=None,
    )
    result = store_themes.get_theme(graph, "meditation-practice")
    assert result.theme.state == "Practiced for 2 weeks."
    assert result.theme.status == ["emerging"]  # unchanged
    assert node_id in result.theme.anchors  # unchanged


def test_update_theme_anchors_add_remove(graph: Graph) -> None:
    n1 = _make_node(graph, "anxiety")
    n2 = _make_node(graph, "calm")
    store_themes.create_theme(
        graph, "mental-health", "Exploring emotions.", [n1], ["active"]
    )

    # Replace n1 with n2
    store_themes.update_theme(
        graph, "mental-health", new_state=None, new_anchors=[n2], new_status=None
    )
    result = store_themes.get_theme(graph, "mental-health")
    assert n1 not in result.theme.anchors
    assert n2 in result.theme.anchors


def test_update_theme_status(graph: Graph) -> None:
    store_themes.create_theme(graph, "pottery-class", "Casual hobby.", [], ["emerging"])
    store_themes.update_theme(
        graph,
        "pottery-class",
        new_state=None,
        new_anchors=None,
        new_status=["deep", "active"],
    )
    result = store_themes.get_theme(graph, "pottery-class")
    assert set(result.theme.status) == {"deep", "active"}


def test_update_theme_invalid_anchor(graph: Graph) -> None:
    store_themes.create_theme(graph, "reading", "Reading widely.", [], ["active"])
    with pytest.raises(ValueError, match="not found as SemanticNode"):
        store_themes.update_theme(
            graph, "reading", new_state=None, new_anchors=["node:999"], new_status=None
        )


def test_update_theme_not_found(graph: Graph) -> None:
    with pytest.raises(ValueError, match="not found"):
        store_themes.update_theme(
            graph, "nonexistent", new_state="x", new_anchors=None, new_status=None
        )


# ---------------------------------------------------------------------------
# retire_theme
# ---------------------------------------------------------------------------


def test_retire_theme(graph: Graph) -> None:
    node_id = _make_node(graph, "running")
    store_themes.create_theme(
        graph, "exercise", "Building fitness habit.", [node_id], ["active"]
    )
    store_themes.retire_theme(graph, "exercise")
    with pytest.raises(ValueError, match="not found"):
        store_themes.get_theme(graph, "exercise")

    # ANCHORS edges should be gone
    result = graph.query("MATCH ()-[r:ANCHORS]->() RETURN count(r)")
    assert result.result_set[0][0] == 0


def test_retire_theme_not_found(graph: Graph) -> None:
    with pytest.raises(ValueError, match="not found"):
        store_themes.retire_theme(graph, "nonexistent")


# ---------------------------------------------------------------------------
# list_all_themes
# ---------------------------------------------------------------------------


def test_list_all_themes_empty(graph: Graph) -> None:
    assert store_themes.list_all_themes(graph) == []


def test_list_all_themes_multiple(graph: Graph) -> None:
    n1 = _make_node(graph, "work")
    store_themes.create_theme(graph, "career", "Career focus.", [n1], ["active"])
    store_themes.create_theme(graph, "health", "Health matters.", [], ["emerging"])
    themes = store_themes.list_all_themes(graph)
    names = {t.name for t in themes}
    assert names == {"career", "health"}


# ---------------------------------------------------------------------------
# render_hot_themes (pure function)
# ---------------------------------------------------------------------------


def test_render_hot_themes_empty() -> None:
    hot, cold = store_themes.render_hot_themes([], [], 250)
    assert hot == ""
    assert cold == []


def test_render_hot_themes_budget_respected() -> None:
    # Create many themes; budget is tiny so only a few fit
    themes = [
        Theme(
            name=f"theme-{i}",
            state=f"Long state description for theme number {i}.",
            status=["active"],
            anchors=[],
        )
        for i in range(20)
    ]
    priority_order = [f"theme-{i}" for i in range(20)]
    hot, cold = store_themes.render_hot_themes(themes, priority_order, 100)
    # Some themes should be cold
    assert len(cold) > 0
    # Hot themes should appear in hot block
    assert "HOT THEMES" in hot


def test_render_hot_themes_cold_index_in_output() -> None:
    # Make theme-b's state very long so only theme-a fits in a tight budget
    themes = [
        Theme(name="theme-a", state="Short.", status=["deep"], anchors=[]),
        Theme(
            name="theme-b",
            state="A very long state description that will certainly push the cumulative token count over any reasonable small budget.",
            status=["emerging"],
            anchors=[],
        ),
    ]
    # Use a budget that fits theme-a but not theme-b together
    hot, cold = store_themes.render_hot_themes(themes, ["theme-a", "theme-b"], 20)
    assert "theme-b" in cold
    assert "Other themes" in hot


def test_render_hot_themes_invalid_priority_order() -> None:
    theme = Theme(name="career", state="state", status=["active"], anchors=[])
    with pytest.raises(ValueError, match="unknown theme name"):
        store_themes.render_hot_themes([theme], ["career", "unknown-name"], 250)
