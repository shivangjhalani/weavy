from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from falkordb import Graph
from pydantic import BaseModel

from weavy.models.tools import (
    CompleteIngestionInput,
    CompleteThemeUpdateInput,
    CreateEdgeInput,
    CreateNodeInput,
    CreateThemeInput,
    DeleteEdgeInput,
    DeleteNodeInput,
    DeliverResponseInput,
    GetChatInput,
    GetNodeInput,
    GetNodeNeighborhoodInput,
    GetThemeInput,
    GetTranscriptSpanInput,
    ListChatsInput,
    ListTranscriptsInput,
    OperationResult,
    RetireThemeInput,
    SearchGraphInput,
    UpdateEdgeInput,
    UpdateNodeInput,
    UpdateThemeInput,
)
from weavy.models.traces import RunTrace, graph_delta
from weavy.services import memory
from weavy.store import canonical as store_canonical
from weavy.store import graph as store_graph
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


def complete_ingestion(
    params: CompleteIngestionInput, ctx: ActionContext
) -> OperationResult:
    ctx.trace.completion_payload = {
        **params.model_dump(),
        **graph_delta(ctx.trace.touched_nodes, ctx.trace.touched_edges),
    }
    return OperationResult(ok=True)


def deliver_response(
    params: DeliverResponseInput, ctx: ActionContext
) -> OperationResult:
    ctx.trace.completion_payload = params.model_dump()
    return OperationResult(ok=True)


def complete_theme_update(
    params: CompleteThemeUpdateInput,
    ctx: ActionContext,
) -> OperationResult:
    ctx.trace.completion_payload = params.model_dump()
    return OperationResult(ok=True)


ACTIONS: dict[str, Action] = {
    "search_graph": Action(
        "search_graph",
        "Search semantic nodes by keyword.",
        SearchGraphInput,
        lambda p, ctx: store_graph.search_graph(ctx.graph, p),
    ),
    "get_node": Action(
        "get_node",
        "Get one or more semantic nodes by id.",
        GetNodeInput,
        lambda p, ctx: memory.get_node(ctx.graph, p),
    ),
    "get_node_neighborhood": Action(
        "get_node_neighborhood",
        "Get a node with its neighbors.",
        GetNodeNeighborhoodInput,
        lambda p, ctx: store_graph.get_node_neighborhood(ctx.graph, p.node_id),
    ),
    "list_transcripts": Action(
        "list_transcripts",
        "List transcript records.",
        ListTranscriptsInput,
        lambda p, ctx: store_canonical.list_transcripts(ctx.graph, p),
    ),
    "get_transcript_span": Action(
        "get_transcript_span",
        "Get one or more transcript spans.",
        GetTranscriptSpanInput,
        lambda p, ctx: memory.get_transcript_span(ctx.graph, p),
    ),
    "list_chats": Action(
        "list_chats",
        "List chat sessions.",
        ListChatsInput,
        lambda p, ctx: store_canonical.list_chats(ctx.graph, p),
    ),
    "get_chat": Action(
        "get_chat",
        "Get a chat session or slice.",
        GetChatInput,
        lambda p, ctx: store_canonical.get_chat(
            ctx.graph, p.chat_id, p.start_index, p.end_index
        ),
    ),
    "get_theme": Action(
        "get_theme",
        "Get a theme by name.",
        GetThemeInput,
        lambda p, ctx: store_themes.get_theme(ctx.graph, p.name),
    ),
    "create_node": Action(
        "create_node",
        "Create a semantic node.",
        CreateNodeInput,
        lambda p, ctx: memory.create_node(ctx.graph, p, ctx.trace),
    ),
    "update_node": Action(
        "update_node",
        "Update a semantic node.",
        UpdateNodeInput,
        lambda p, ctx: memory.update_node(ctx.graph, p, ctx.trace),
    ),
    "delete_node": Action(
        "delete_node",
        "Delete a semantic node.",
        DeleteNodeInput,
        lambda p, ctx: memory.delete_node(ctx.graph, p, ctx.trace),
    ),
    "create_edge": Action(
        "create_edge",
        "Create a semantic edge.",
        CreateEdgeInput,
        lambda p, ctx: memory.create_edge(ctx.graph, p, ctx.trace),
    ),
    "update_edge": Action(
        "update_edge",
        "Update a semantic edge.",
        UpdateEdgeInput,
        lambda p, ctx: memory.update_edge(ctx.graph, p, ctx.trace),
    ),
    "delete_edge": Action(
        "delete_edge",
        "Delete a semantic edge.",
        DeleteEdgeInput,
        lambda p, ctx: memory.delete_edge(ctx.graph, p, ctx.trace),
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
    "complete_ingestion": Action(
        "complete_ingestion",
        "Finish an ingestion run.",
        CompleteIngestionInput,
        complete_ingestion,
        is_completion=True,
    ),
    "deliver_response": Action(
        "deliver_response",
        "Finish a query run.",
        DeliverResponseInput,
        deliver_response,
        is_completion=True,
    ),
    "complete_theme_update": Action(
        "complete_theme_update",
        "Finish a theme update run.",
        CompleteThemeUpdateInput,
        complete_theme_update,
        is_completion=True,
    ),
}

GRAPH_READ_ACTIONS = [
    "search_graph",
    "get_node",
    "get_node_neighborhood",
    "list_transcripts",
    "get_transcript_span",
    "list_chats",
    "get_chat",
]

GRAPH_WRITE_ACTIONS = [
    "create_node",
    "update_node",
    "delete_node",
    "create_edge",
    "update_edge",
    "delete_edge",
]

INGESTION_ACTIONS = GRAPH_READ_ACTIONS + GRAPH_WRITE_ACTIONS + ["complete_ingestion"]
# Query mode includes reads, writes (conversational graph mutation), and theme lookup
QUERY_ACTIONS = (
    GRAPH_READ_ACTIONS + GRAPH_WRITE_ACTIONS + ["get_theme", "deliver_response"]
)
THEME_ACTIONS = [
    "search_graph",
    "get_node",
    "get_node_neighborhood",
    "get_theme",
    "create_theme",
    "update_theme",
    "retire_theme",
    "complete_theme_update",
]


def get_action_definitions(names: list[str]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": ACTIONS[name].name,
                "description": ACTIONS[name].description,
                "parameters": ACTIONS[name].input_model.model_json_schema(),
            },
        }
        for name in names
    ]
