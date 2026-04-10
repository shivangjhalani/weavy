"""
Theme persistence — Theme node CRUD in FalkorDB.
Anchors are stored as a flat list property on the Theme node — no graph edges.
"""

from functools import lru_cache

from falkordb import Graph

from weavy.models.themes import Theme, ThemeStatus
from weavy.models.tools import GetThemeOutput, OperationResult


@lru_cache(maxsize=1)
def _get_enc():
    """cl100k_base is a heuristic proxy — Gemini uses a different tokenizer but
    exact counts are unavailable via LiteLLM. Close enough for budget gating."""
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def _theme_from_props(t_props: dict) -> Theme:
    return Theme(
        name=t_props["name"],
        state=t_props["state"],
        status=t_props.get("status", []),
        anchors=t_props.get("anchors", []),
    )


def create_theme(
    graph: Graph,
    name: str,
    state: str,
    anchors: list[str],
    status: list[ThemeStatus],
) -> OperationResult:
    graph.query(
        "CREATE (t:Theme {name: $name, state: $state, status: $status, anchors: $anchors})",
        {
            "name": name,
            "state": state,
            "status": list(status),
            "anchors": list(anchors),
        },
    )
    return OperationResult(ok=True, id=name)


def get_theme(graph: Graph, name: str) -> GetThemeOutput:
    result = graph.query(
        "MATCH (t:Theme {name: $name}) RETURN t",
        {"name": name},
    )
    if not result.result_set:
        raise ValueError(f"Theme '{name}' not found.")
    t_props = result.result_set[0][0].properties
    return GetThemeOutput(theme=_theme_from_props(t_props))


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
    result = graph.query("MATCH (t:Theme) RETURN t")
    return [_theme_from_props(row[0].properties) for row in result.result_set]


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
        token_count = len(_get_enc().encode(rendered))

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
