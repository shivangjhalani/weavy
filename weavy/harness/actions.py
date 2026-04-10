from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from falkordb import Graph
from pydantic import BaseModel

from weavy.application.contracts import GetSessionOutput, GetThemeOutput, OperationResult
from weavy.harness.tool_models import (
    CompleteInput,
    CompleteThemeUpdateInput,
    CreateEdgeInput,
    CreateNodeInput,
    CreateThemeInput,
    DeleteEdgeInput,
    DeleteNodeInput,
    GetNodeInput,
    GetNodeNeighborhoodInput,
    GetSessionInput,
    GetThemeInput,
    ListSessionsInput,
    RetireThemeInput,
    SearchGraphInput,
    SetPrefaceInput,
    UpdateEdgeInput,
    UpdateNodeInput,
    UpdateThemeInput,
)
from weavy.models.traces import RunTrace
from weavy.services import memory
from weavy.store import canonical as store_canonical
from weavy.store import graph as store_graph
from weavy.store import system as store_system
from weavy.store import themes as store_themes


@dataclass
class ActionContext:
    graph: Graph
    trace: RunTrace


@dataclass
class Action:
    name: str
    description: str
    input_model: type[BaseModel]
    fn: Callable[[Any, ActionContext], Any]
    is_completion: bool = False


def _complete(params: Any, ctx: ActionContext) -> OperationResult:
    ctx.trace.completion_payload = params.model_dump()
    return OperationResult(ok=True)


ACTIONS: dict[str, Action] = {
    "search_graph": Action(
        "search_graph",
        "Hybrid search over semantic nodes — combines semantic similarity (embedding) with keyword matching on aliases and summaries. Use varied phrasings to maximize recall; synonyms and rephrasings are matched by the vector component even when exact keywords differ.",
        SearchGraphInput,
        lambda p, ctx: memory.search_graph(ctx.graph, query=p.query, limit=p.limit),
    ),
    "get_node": Action(
        "get_node",
        "Get one or more semantic nodes by id.",
        GetNodeInput,
        lambda p, ctx: memory.get_node(ctx.graph, node_ids=p.node_ids),
    ),
    "get_node_neighborhood": Action(
        "get_node_neighborhood",
        "Get a node with its neighbors.",
        GetNodeNeighborhoodInput,
        lambda p, ctx: store_graph.get_node_neighborhood(ctx.graph, p.node_id),
    ),
    "list_sessions": Action(
        "list_sessions",
        "List sessions (transcripts and chats).",
        ListSessionsInput,
        lambda p, ctx: store_canonical.list_sessions(
            ctx.graph, limit=p.limit, date_range=p.date_range
        ),
    ),
    "get_session": Action(
        "get_session",
        "Get a session's messages or a slice.",
        GetSessionInput,
        lambda p, ctx: GetSessionOutput(
            session=store_canonical.get_session_messages(
                ctx.graph, p.session_id, p.start_index, p.end_index
            )
        ),
    ),
    "get_theme": Action(
        "get_theme",
        "Get a theme by name.",
        GetThemeInput,
        lambda p, ctx: GetThemeOutput(theme=store_themes.get_theme(ctx.graph, p.name)),
    ),
    "create_node": Action(
        "create_node",
        "Create a semantic node.",
        CreateNodeInput,
        lambda p, ctx: memory.create_node(
            ctx.graph,
            aliases=p.aliases,
            summary=p.summary,
            note=p.note,
            provenance=p.provenance,
            trace=ctx.trace,
        ),
    ),
    "update_node": Action(
        "update_node",
        "Update a semantic node.",
        UpdateNodeInput,
        lambda p, ctx: memory.update_node(
            ctx.graph,
            node_id=p.node_id,
            note=p.note,
            provenance=p.provenance,
            trace=ctx.trace,
            new_summary=p.new_summary,
            new_aliases=p.new_aliases,
        ),
    ),
    "delete_node": Action(
        "delete_node",
        "Delete a semantic node.",
        DeleteNodeInput,
        lambda p, ctx: memory.delete_node(
            ctx.graph, node_id=p.node_id, trace=ctx.trace
        ),
    ),
    "create_edge": Action(
        "create_edge",
        "Create a semantic edge between two nodes. Both node IDs must already exist in the graph — use only IDs returned by prior create_node calls, never IDs of nodes being created in the same batch. Requires a label (short relationship type) and a note (why this relationship exists).",
        CreateEdgeInput,
        lambda p, ctx: memory.create_edge(
            ctx.graph,
            from_node_id=p.from_node_id,
            to_node_id=p.to_node_id,
            label=p.label,
            note=p.note,
            trace=ctx.trace,
        ),
    ),
    "update_edge": Action(
        "update_edge",
        "Update a semantic edge.",
        UpdateEdgeInput,
        lambda p, ctx: memory.update_edge(
            ctx.graph, edge_id=p.edge_id, new_label=p.new_label, trace=ctx.trace
        ),
    ),
    "delete_edge": Action(
        "delete_edge",
        "Delete a semantic edge.",
        DeleteEdgeInput,
        lambda p, ctx: memory.delete_edge(
            ctx.graph, edge_id=p.edge_id, trace=ctx.trace
        ),
    ),
    "create_theme": Action(
        "create_theme",
        "Create a theme.",
        CreateThemeInput,
        lambda p, ctx: store_themes.create_theme(
            ctx.graph, p.name, p.state, p.anchors, p.status
        ),
    ),
    "update_theme": Action(
        "update_theme",
        "Update a theme.",
        UpdateThemeInput,
        lambda p, ctx: store_themes.update_theme(
            ctx.graph, p.name, p.new_state, p.new_anchors, p.new_status
        ),
    ),
    "retire_theme": Action(
        "retire_theme",
        "Retire a theme.",
        RetireThemeInput,
        lambda p, ctx: store_themes.retire_theme(ctx.graph, p.name),
    ),
    "set_preface": Action(
        "set_preface",
        "Set or update the graph preface — a short description of what this graph is about and whose it is.",
        SetPrefaceInput,
        lambda p, ctx: store_system.set_preface(ctx.graph, p.preface)
        or OperationResult(ok=True),
    ),
    "complete": Action(
        "complete",
        "Finish a session run.",
        CompleteInput,
        _complete,
        is_completion=True,
    ),
    "complete_theme_update": Action(
        "complete_theme_update",
        "Finish a theme update run.",
        CompleteThemeUpdateInput,
        _complete,
        is_completion=True,
    ),
}

GRAPH_READ_ACTIONS = [
    "search_graph",
    "get_node",
    "get_node_neighborhood",
    "list_sessions",
    "get_session",
]

GRAPH_WRITE_ACTIONS = [
    "create_node",
    "update_node",
    "delete_node",
    "create_edge",
    "update_edge",
    "delete_edge",
]

SESSION_ACTIONS = GRAPH_READ_ACTIONS + GRAPH_WRITE_ACTIONS + ["get_theme", "complete"]

THEME_ACTIONS = GRAPH_READ_ACTIONS + [
    "get_theme",
    "create_theme",
    "update_theme",
    "retire_theme",
    "set_preface",
    "complete_theme_update",
]


def _slim_schema(schema: dict) -> dict:
    """Compact a Pydantic JSON schema for LLM tool definitions.

    Resolves $ref pointers inline, strips title fields, and simplifies
    Optional (anyOf-with-null) wrappers so the schema is shorter in tokens.
    """
    defs = schema.get("$defs", {})

    def _resolve(node: object) -> object:
        if isinstance(node, list):
            return [_resolve(item) for item in node]
        if not isinstance(node, dict):
            return node

        if "$ref" in node:
            ref = node["$ref"].rsplit("/", 1)[-1]
            return _resolve(dict(defs[ref])) if ref in defs else node

        if "anyOf" in node:
            non_null = [v for v in node["anyOf"] if v != {"type": "null"}]
            has_null = any(v == {"type": "null"} for v in node["anyOf"])
            if len(non_null) == 1 and has_null:
                merged = _resolve(non_null[0])
                if isinstance(merged, dict):
                    for k, v in node.items():
                        if k not in ("anyOf", "title"):
                            merged.setdefault(k, v)
                return merged

        return {k: _resolve(v) for k, v in node.items() if k not in ("title", "$defs")}

    return _resolve(schema)  # type: ignore[return-value]


def get_action_definitions(names: list[str]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": ACTIONS[name].name,
                "description": ACTIONS[name].description,
                "parameters": _slim_schema(
                    ACTIONS[name].input_model.model_json_schema()
                ),
            },
        }
        for name in names
    ]
