"""
Theme CRUD, anchor management, and hot-theme rendering.
Requires a running FalkorDB instance (provided by devenv up).
Uses the "weavy_test" graph to avoid touching the main graph.
"""

import pytest
from falkordb import Graph

from weavy.models.themes import Theme
from weavy.store import themes as store_themes
from tests.helpers import reset_test_graph


@pytest.fixture
def graph() -> Graph:
    return reset_test_graph("Theme")


# ---------------------------------------------------------------------------
# create_theme / get_theme
# ---------------------------------------------------------------------------


def test_create_theme_basic(graph: Graph) -> None:
    store_themes.create_theme(
        graph, "career-direction", "Weighing a job change.", ["node:1"], ["active"]
    )
    result = store_themes.get_theme(graph, "career-direction")
    theme = result.theme
    assert theme.name == "career-direction"
    assert theme.state == "Weighing a job change."
    assert theme.status == ["active"]
    assert "node:1" in theme.anchors


def test_create_theme_no_anchors(graph: Graph) -> None:
    store_themes.create_theme(
        graph, "sleep-routine", "Tracking sleep.", [], ["emerging"]
    )
    result = store_themes.get_theme(graph, "sleep-routine")
    assert result.theme.anchors == []


def test_get_theme_not_found(graph: Graph) -> None:
    with pytest.raises(ValueError, match="not found"):
        store_themes.get_theme(graph, "nonexistent")


# ---------------------------------------------------------------------------
# update_theme
# ---------------------------------------------------------------------------


def test_update_theme_state_only(graph: Graph) -> None:
    store_themes.create_theme(
        graph, "meditation-practice", "Just started.", ["node:1"], ["emerging"]
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
    assert "node:1" in result.theme.anchors  # unchanged


def test_update_theme_anchors_add_remove(graph: Graph) -> None:
    store_themes.create_theme(
        graph, "mental-health", "Exploring emotions.", ["node:1"], ["active"]
    )
    store_themes.update_theme(
        graph, "mental-health", new_state=None, new_anchors=["node:2"], new_status=None
    )
    result = store_themes.get_theme(graph, "mental-health")
    assert "node:1" not in result.theme.anchors
    assert "node:2" in result.theme.anchors


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


def test_update_theme_not_found(graph: Graph) -> None:
    with pytest.raises(ValueError, match="not found"):
        store_themes.update_theme(
            graph, "nonexistent", new_state="x", new_anchors=None, new_status=None
        )


# ---------------------------------------------------------------------------
# retire_theme
# ---------------------------------------------------------------------------


def test_retire_theme(graph: Graph) -> None:
    store_themes.create_theme(
        graph, "exercise", "Building fitness habit.", ["node:1"], ["active"]
    )
    store_themes.retire_theme(graph, "exercise")
    with pytest.raises(ValueError, match="not found"):
        store_themes.get_theme(graph, "exercise")


def test_retire_theme_not_found(graph: Graph) -> None:
    with pytest.raises(ValueError, match="not found"):
        store_themes.retire_theme(graph, "nonexistent")


# ---------------------------------------------------------------------------
# list_all_themes
# ---------------------------------------------------------------------------


def test_list_all_themes_empty(graph: Graph) -> None:
    assert store_themes.list_all_themes(graph) == []


def test_list_all_themes_multiple(graph: Graph) -> None:
    store_themes.create_theme(graph, "career", "Career focus.", ["node:1"], ["active"])
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
    assert len(cold) > 0
    assert "HOT THEMES" in hot


def test_render_hot_themes_cold_index_in_output() -> None:
    themes = [
        Theme(name="theme-a", state="Short.", status=["deep"], anchors=[]),
        Theme(
            name="theme-b",
            state="A very long state description that will certainly push the cumulative token count over any reasonable small budget.",
            status=["emerging"],
            anchors=[],
        ),
    ]
    hot, cold = store_themes.render_hot_themes(themes, ["theme-a", "theme-b"], 20)
    assert "theme-b" in cold
    assert "Other themes" in hot


def test_render_hot_themes_invalid_priority_order() -> None:
    theme = Theme(name="career", state="state", status=["active"], anchors=[])
    with pytest.raises(ValueError, match="unknown theme name"):
        store_themes.render_hot_themes([theme], ["career", "unknown-name"], 250)
