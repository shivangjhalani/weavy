"""
Theme persistence — Theme node CRUD and anchor edge management in FalkorDB.
"""

import json

import tiktoken
from falkordb import Graph

from weavy.models.themes import Theme, ThemeStatus
from weavy.models.tools import GetThemeOutput, OperationResult

_ENC = tiktoken.get_encoding("cl100k_base")


def _parse_status(raw: list | str | None) -> list[ThemeStatus]:
    """Parse status from DB (may be list or JSON string)."""
    if isinstance(raw, str):
        return json.loads(raw)
    return list(raw) if raw else []


def _validate_anchors(graph: Graph, anchor_ids: list[str]) -> None:
    """Raise ValueError if any anchor_ids do not exist as SemanticNodes."""
    if not anchor_ids:
        return
    result = graph.query(
        "MATCH (n:SemanticNode) WHERE n.id IN $ids RETURN n.id",
        {"ids": anchor_ids},
    )
    found = {row[0] for row in result.result_set}
    missing = [a for a in anchor_ids if a not in found]
    if missing:
        raise ValueError(f"Anchor target(s) not found as SemanticNode: {', '.join(missing)}")


def create_theme(
    graph: Graph,
    name: str,
    state: str,
    anchors: list[str],
    status: list[ThemeStatus],
) -> OperationResult:
    _validate_anchors(graph, anchors)

    graph.query(
        "CREATE (t:Theme {name: $name, state: $state, status: $status})",
        {"name": name, "state": state, "status": list(status)},
    )

    for anchor_id in anchors:
        graph.query(
            """
            MATCH (t:Theme {name: $name}), (n:SemanticNode {id: $anchor_id})
            CREATE (t)-[:ANCHORS]->(n)
            """,
            {"name": name, "anchor_id": anchor_id},
        )

    return OperationResult(ok=True, id=name)


def get_theme(graph: Graph, name: str) -> GetThemeOutput:
    result = graph.query(
        """
        MATCH (t:Theme {name: $name})
        OPTIONAL MATCH (t)-[:ANCHORS]->(n:SemanticNode)
        RETURN t, collect(n.id) AS anchor_ids
        """,
        {"name": name},
    )
    if not result.result_set:
        raise ValueError(f"Theme '{name}' not found.")

    row = result.result_set[0]
    t_props = row[0].properties
    anchor_ids = [a for a in (row[1] or []) if a is not None]

    theme = Theme(
        name=t_props["name"],
        state=t_props["state"],
        status=_parse_status(t_props.get("status", [])),
        anchors=anchor_ids,
    )
    return GetThemeOutput(theme=theme)


def update_theme(
    graph: Graph,
    name: str,
    new_state: str | None,
    new_anchors: list[str] | None,
    new_status: list[ThemeStatus] | None,
) -> OperationResult:
    result = graph.query(
        "MATCH (t:Theme {name: $name}) RETURN t",
        {"name": name},
    )
    if not result.result_set:
        raise ValueError(f"Theme '{name}' not found.")

    set_parts = []
    params: dict = {"name": name}
    if new_state is not None:
        set_parts.append("t.state = $new_state")
        params["new_state"] = new_state
    if new_status is not None:
        set_parts.append("t.status = $new_status")
        params["new_status"] = list(new_status)

    if set_parts:
        graph.query(
            f"MATCH (t:Theme {{name: $name}}) SET {', '.join(set_parts)}",
            params,
        )

    if new_anchors is not None:
        _validate_anchors(graph, new_anchors)

        # Get current anchors
        result = graph.query(
            "MATCH (t:Theme {name: $name})-[:ANCHORS]->(n:SemanticNode) RETURN n.id",
            {"name": name},
        )
        current_set = {row[0] for row in result.result_set}
        new_set = set(new_anchors)

        for anchor_id in new_set - current_set:
            graph.query(
                """
                MATCH (t:Theme {name: $name}), (n:SemanticNode {id: $anchor_id})
                CREATE (t)-[:ANCHORS]->(n)
                """,
                {"name": name, "anchor_id": anchor_id},
            )

        for anchor_id in current_set - new_set:
            graph.query(
                """
                MATCH (t:Theme {name: $name})-[r:ANCHORS]->(n:SemanticNode {id: $anchor_id})
                DELETE r
                """,
                {"name": name, "anchor_id": anchor_id},
            )

    return OperationResult(ok=True, id=name)


def retire_theme(graph: Graph, name: str) -> OperationResult:
    result = graph.query(
        "MATCH (t:Theme {name: $name}) RETURN t",
        {"name": name},
    )
    if not result.result_set:
        raise ValueError(f"Theme '{name}' not found.")

    graph.query(
        "MATCH (t:Theme {name: $name}) DETACH DELETE t",
        {"name": name},
    )
    return OperationResult(ok=True, id=name)


def list_all_themes(graph: Graph) -> list[Theme]:
    result = graph.query(
        """
        MATCH (t:Theme)
        OPTIONAL MATCH (t)-[:ANCHORS]->(n:SemanticNode)
        RETURN t, collect(n.id) AS anchor_ids
        """
    )
    themes = []
    seen: set[str] = set()
    for row in result.result_set:
        t_props = row[0].properties
        name = t_props["name"]
        if name in seen:
            continue
        seen.add(name)
        anchor_ids = [a for a in (row[1] or []) if a is not None]
        themes.append(
            Theme(
                name=name,
                state=t_props["state"],
                status=_parse_status(t_props.get("status", [])),
                anchors=anchor_ids,
            )
        )
    return themes


def render_hot_themes(
    themes: list[Theme],
    priority_order: list[str],
    token_budget: int,
) -> tuple[str, list[str]]:
    """
    Pure function. Returns (rendered_hot_block, cold_theme_names).

    Walks priority_order top-down, rendering each theme until the token budget
    is exhausted. Fails loudly if priority_order contains unknown theme names.
    """
    if not themes:
        return ("", [])

    theme_map = {t.name: t for t in themes}

    for name in priority_order:
        if name not in theme_map:
            raise ValueError(f"Priority order contains unknown theme name: '{name}'")

    hot_parts: list[str] = []
    cold_names: list[str] = []
    tokens_used = 0
    priority_set = set(priority_order)

    for name in priority_order:
        theme = theme_map[name]
        rendered = theme.render_block()
        token_count = len(_ENC.encode(rendered))

        if tokens_used + token_count <= token_budget:
            hot_parts.append(rendered)
            tokens_used += token_count
        else:
            cold_names.append(name)

    # Themes not in priority_order fall to cold index
    for theme in themes:
        if theme.name not in priority_set:
            cold_names.append(theme.name)

    if not hot_parts:
        return ("", cold_names)

    total = len(themes)
    hot_count = len(hot_parts)
    header = f"HOT THEMES ({hot_count} of {total} themes, filling {tokens_used} of {token_budget} token budget)\n\n"
    hot_block = header + "\n\n".join(hot_parts)

    if cold_names:
        hot_block += "\n\nOther themes: " + ", ".join(cold_names)

    return (hot_block, cold_names)


def build_themes_context(
    graph: Graph,
    priority_order: list[str],
    budget: int,
    empty_msg: str = "(No themes yet.)",
) -> str:
    """Render the themes context block for a system prompt."""
    all_themes = list_all_themes(graph)
    hot_block, cold_names = render_hot_themes(all_themes, priority_order, budget)

    if hot_block:
        return hot_block
    if cold_names:
        return "Themes (no hot set rendered): " + ", ".join(cold_names)
    return empty_msg
