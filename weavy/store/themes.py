"""
Theme persistence — Theme node CRUD in FalkorDB.
Anchors are stored as a flat list property on the Theme node — no graph edges.
"""

from falkordb import Graph

from weavy.application.contracts import OperationResult
from weavy.models.themes import THEME_PRIORITY_UNSET, Theme, ThemeStatus


def _theme_from_props(t_props: dict) -> Theme:
    return Theme(
        name=t_props["name"],
        state=t_props["state"],
        status=t_props.get("status", []),
        anchors=t_props.get("anchors", []),
        priority=t_props.get("priority", THEME_PRIORITY_UNSET),
    )


def create_theme(
    graph: Graph,
    name: str,
    state: str,
    anchors: list[str],
    status: list[ThemeStatus],
) -> OperationResult:
    graph.query(
        "CREATE (t:Theme {name: $name, state: $state, status: $status, "
        "anchors: $anchors, priority: $priority})",
        {
            "name": name,
            "state": state,
            "status": list(status),
            "anchors": list(anchors),
            # New theme sorts last until the next theme-run reconciles ranks.
            "priority": THEME_PRIORITY_UNSET,
        },
    )
    return OperationResult(ok=True, id=name)


def get_theme(graph: Graph, name: str) -> Theme:
    result = graph.query(
        "MATCH (t:Theme {name: $name}) RETURN t",
        {"name": name},
    )
    if not result.result_set:
        raise ValueError(f"Theme '{name}' not found.")
    t_props = result.result_set[0][0].properties
    return _theme_from_props(t_props)


def update_theme(
    graph: Graph,
    name: str,
    new_state: str | None,
    new_anchors: list[str] | None,
    new_status: list[ThemeStatus] | None,
) -> OperationResult:
    set_parts = []
    params: dict = {"name": name}
    if new_state is not None:
        set_parts.append("t.state = $new_state")
        params["new_state"] = new_state
    if new_status is not None:
        set_parts.append("t.status = $new_status")
        params["new_status"] = list(new_status)
    if new_anchors is not None:
        set_parts.append("t.anchors = $new_anchors")
        params["new_anchors"] = list(new_anchors)

    query = "MATCH (t:Theme {name: $name})"
    if set_parts:
        query += f" SET {', '.join(set_parts)}"
    result = graph.query(query + " RETURN t", params)
    if not result.result_set:
        raise ValueError(f"Theme '{name}' not found.")

    return OperationResult(ok=True, id=name)


def retire_theme(graph: Graph, name: str) -> OperationResult:
    result = graph.query(
        "MATCH (t:Theme {name: $name}) DETACH DELETE t RETURN count(t)",
        {"name": name},
    )
    deleted = result.result_set[0][0] if result.result_set else 0
    if deleted == 0:
        raise ValueError(f"Theme '{name}' not found.")
    return OperationResult(ok=True, id=name)


def list_all_themes(graph: Graph) -> list[Theme]:
    """All themes in salience order (most salient first). Order is intrinsic to the
    themes (their ``priority`` rank), not a separate list — so it can never reference
    a theme that does not exist."""
    result = graph.query("MATCH (t:Theme) RETURN t ORDER BY t.priority, t.name")
    return [_theme_from_props(row[0].properties) for row in result.result_set]


def set_theme_priority(graph: Graph, ordered_names: list[str]) -> None:
    """Project a salience ordering onto the themes: each name gets rank = its index.

    Names that do not match a theme simply update nothing — there is no separate list
    to fall out of sync, so an unknown name is harmless rather than a hard error.
    """
    if not ordered_names:
        return
    graph.query(
        """
        UNWIND range(0, size($names) - 1) AS i
        MATCH (t:Theme {name: $names[i]})
        SET t.priority = i
        """,
        {"names": ordered_names},
    )
