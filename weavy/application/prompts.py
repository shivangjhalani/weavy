from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from falkordb import Graph

from weavy.models.themes import Theme
from weavy.store import themes as store_themes
from weavy.store.system import SystemState


@lru_cache(maxsize=None)
def _load_prompt_template(name: str) -> str:
    prompts_dir = Path(__file__).parent.parent / "prompts"
    for suffix in (".md", ".txt"):
        path = prompts_dir / f"{name}{suffix}"
        try:
            return path.read_text()
        except (FileNotFoundError, OSError):
            continue
    raise FileNotFoundError(
        f"No prompt template {name!r} (.md or .txt) in {prompts_dir}"
    )


def fetch_prompt(name: str, variables: dict[str, object]) -> str:
    template = _load_prompt_template(name)
    for key, value in variables.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


@lru_cache(maxsize=1)
def _get_theme_tokenizer():
    """Use cl100k_base as an approximate tokenizer for prompt budgeting."""
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def render_hot_themes(
    themes: list[Theme],
    priority_order: list[str],
    token_budget: int,
) -> tuple[str, list[str]]:
    if not themes:
        return ("", [])

    theme_map = {theme.name: theme for theme in themes}

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
        token_count = len(_get_theme_tokenizer().encode(rendered))
        if tokens_used + token_count <= token_budget:
            hot_parts.append(rendered)
            tokens_used += token_count
        else:
            cold_names.append(name)

    for theme in themes:
        if theme.name not in priority_set:
            cold_names.append(theme.name)

    if not hot_parts:
        return ("", cold_names)

    total = len(themes)
    hot_count = len(hot_parts)
    header = (
        f"HOT THEMES ({hot_count} of {total} themes, filling "
        f"{tokens_used} of {token_budget} token budget)\n\n"
    )
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
    all_themes = store_themes.list_all_themes(graph)
    hot_block, cold_names = render_hot_themes(all_themes, priority_order, budget)

    if hot_block:
        return hot_block
    if cold_names:
        return "Themes (no hot set rendered): " + ", ".join(cold_names)
    return empty_msg


def build_themed_system_prompt(
    prompt_name: str,
    graph: Graph,
    system_state: SystemState,
    empty_themes_message: str,
    variables: dict[str, object] | None = None,
    current_time: str | None = None,
    caller_context: str | None = None,
) -> str:
    prompt_variables = dict(variables or {})
    prompt_variables["current_time"] = (
        current_time or datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    )
    prompt_variables["preface"] = (
        system_state.preface or "(not set — call set_preface to describe this graph)"
    )
    prompt_variables["themes_context"] = build_themes_context(
        graph,
        system_state.theme_priority_order,
        system_state.hot_theme_token_budget,
        empty_msg=empty_themes_message,
    )
    prompt_variables["caller_context"] = (
        f"- **Caller context:** {caller_context}" if caller_context else ""
    )
    return fetch_prompt(prompt_name, prompt_variables)


def render_full_theme_map(themes: list[Theme], priority_order: list[str]) -> str:
    if not themes:
        return "CURRENT THEME MAP: (empty — no themes yet)\n"

    lines = ["CURRENT THEME MAP:\n"]
    for theme in themes:
        lines.append(f"{theme.render_block()}\n")
    lines.append(f"\nCurrent priority order: {priority_order}")
    return "\n".join(lines)


def render_session_journal(sessions: list) -> str:
    lines = [f"Sessions since your last run ({len(sessions)}):\n"]
    for i, session in enumerate(sessions, 1):
        changes = session.graph_changes
        change_parts = []
        for action in ("created", "updated", "deleted"):
            node_ids = changes.get(f"nodes_{action}", [])
            edge_ids = changes.get(f"edges_{action}", [])
            if node_ids:
                change_parts.append(f"{action} {', '.join(node_ids)}")
            if edge_ids:
                change_parts.append(f"{action} edges {', '.join(edge_ids)}")
        change_text = "; ".join(change_parts) if change_parts else "no graph changes"
        lines.append(f'{i}. {session.id}: "{session.summary}" — {change_text}')
    return "\n".join(lines)
