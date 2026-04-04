"""
Tool registry — maps tool names to callable functions for each agent mode.
Populated in Phase 4.
"""

from dataclasses import dataclass
from typing import Any, Callable

from falkordb import Graph
from pydantic import BaseModel

from arakne.models.tools import (
    CompleteIngestionInput,
    CompleteThemeUpdateInput,
    CreateEdgeInput,
    CreateNodeInput,
    CreateThemeInput,
    DeleteEdgeInput,
    DeleteNodeInput,
    DeliverResponseInput,
    GetChatInput,
    GetColdLogsInput,
    GetNodeInput,
    GetNodeNeighborhoodInput,
    GetThemeInput,
    GetTranscriptSpanInput,
    ListChatsInput,
    ListTranscriptsInput,
    RetireThemeInput,
    SearchGraphInput,
    UpdateEdgeInput,
    UpdateNodeInput,
    UpdateThemeInput,
)
from arakne.models.traces import RunTrace
from arakne.tools import completion_tools, read_tools, theme_tools, write_tools


@dataclass
class ToolContext:
    graph: Graph
    trace: RunTrace


@dataclass
class ToolEntry:
    name: str
    description: str
    input_model: type[BaseModel]
    fn: Callable[[Any, ToolContext], Any]
    is_mutation: bool = False
    is_completion: bool = False


REGISTRY: dict[str, ToolEntry] = {
    # ---- Graph read tools ----
    "search_graph": ToolEntry(
        name="search_graph",
        description="Search the semantic graph by keyword. Matches node aliases and summary text. Returns nodes ordered by connectivity.",
        input_model=SearchGraphInput,
        fn=lambda p, ctx: read_tools.search_graph(ctx.graph, p),
    ),
    "get_node": ToolEntry(
        name="get_node",
        description="Retrieve a node's full details: summary, aliases, hot log entries, outgoing edges, and cold-log hint if applicable.",
        input_model=GetNodeInput,
        fn=lambda p, ctx: read_tools.get_node(ctx.graph, p),
    ),
    "get_node_neighborhood": ToolEntry(
        name="get_node_neighborhood",
        description="Retrieve a node and its direct neighbors with edge labels and one-line summaries for quick orientation.",
        input_model=GetNodeNeighborhoodInput,
        fn=lambda p, ctx: read_tools.get_node_neighborhood(ctx.graph, p),
    ),
    "get_cold_logs": ToolEntry(
        name="get_cold_logs",
        description="Retrieve archived (cold) log entries for a node — everything at or before the last fence entry.",
        input_model=GetColdLogsInput,
        fn=lambda p, ctx: read_tools.get_cold_logs(ctx.graph, p),
    ),
    "list_transcripts": ToolEntry(
        name="list_transcripts",
        description="List available voice transcripts, optionally filtered by date range.",
        input_model=ListTranscriptsInput,
        fn=lambda p, ctx: read_tools.list_transcripts(ctx.graph, p),
    ),
    "get_transcript_span": ToolEntry(
        name="get_transcript_span",
        description="Retrieve a time-bounded span of transcript text by start and end offset in seconds.",
        input_model=GetTranscriptSpanInput,
        fn=lambda p, ctx: read_tools.get_transcript_span(ctx.graph, p),
    ),
    "list_chats": ToolEntry(
        name="list_chats",
        description="List available chat sessions, optionally filtered by date range.",
        input_model=ListChatsInput,
        fn=lambda p, ctx: read_tools.list_chats(ctx.graph, p),
    ),
    "get_chat": ToolEntry(
        name="get_chat",
        description="Retrieve messages from a chat session, optionally sliced by message index.",
        input_model=GetChatInput,
        fn=lambda p, ctx: read_tools.get_chat(ctx.graph, p),
    ),
    "get_theme": ToolEntry(
        name="get_theme",
        description="Retrieve a theme by name, including its state description, anchor node ids, and status labels.",
        input_model=GetThemeInput,
        fn=lambda p, ctx: read_tools.get_theme(ctx.graph, p),
    ),
    # ---- Graph write tools ----
    "create_node": ToolEntry(
        name="create_node",
        description="Create a new semantic node with aliases, a summary, a provenance-backed note, and provenance metadata.",
        input_model=CreateNodeInput,
        fn=lambda p, ctx: write_tools.create_node(ctx.graph, p, ctx.trace),
        is_mutation=True,
    ),
    "update_node": ToolEntry(
        name="update_node",
        description="Update a semantic node: append a provenance-backed log entry, and optionally rewrite the summary or aliases.",
        input_model=UpdateNodeInput,
        fn=lambda p, ctx: write_tools.update_node(ctx.graph, p, ctx.trace),
        is_mutation=True,
    ),
    "delete_node": ToolEntry(
        name="delete_node",
        description="Delete a semantic node and all its incident edges. Provide a reason.",
        input_model=DeleteNodeInput,
        fn=lambda p, ctx: write_tools.delete_node(ctx.graph, p, ctx.trace),
        is_mutation=True,
    ),
    "create_edge": ToolEntry(
        name="create_edge",
        description="Create a directed RELATES edge between two semantic nodes with a descriptive label. from_node_id and to_node_id must be node:N identifiers (e.g. node:1, node:4) — not aliases or names.",
        input_model=CreateEdgeInput,
        fn=lambda p, ctx: write_tools.create_edge(ctx.graph, p, ctx.trace),
        is_mutation=True,
    ),
    "update_edge": ToolEntry(
        name="update_edge",
        description="Update the label of an existing edge.",
        input_model=UpdateEdgeInput,
        fn=lambda p, ctx: write_tools.update_edge(ctx.graph, p, ctx.trace),
        is_mutation=True,
    ),
    "delete_edge": ToolEntry(
        name="delete_edge",
        description="Delete an edge by id. Provide a reason.",
        input_model=DeleteEdgeInput,
        fn=lambda p, ctx: write_tools.delete_edge(ctx.graph, p, ctx.trace),
        is_mutation=True,
    ),
    # ---- Theme write tools ----
    "create_theme": ToolEntry(
        name="create_theme",
        description="Create a new theme node with name, state description, anchor node ids, and status labels.",
        input_model=CreateThemeInput,
        fn=lambda p, ctx: theme_tools.create_theme(ctx.graph, p, ctx.trace),
        is_mutation=True,
    ),
    "update_theme": ToolEntry(
        name="update_theme",
        description="Update a theme's state description, anchor nodes, or status labels.",
        input_model=UpdateThemeInput,
        fn=lambda p, ctx: theme_tools.update_theme(ctx.graph, p, ctx.trace),
        is_mutation=True,
    ),
    "retire_theme": ToolEntry(
        name="retire_theme",
        description="Retire a theme, marking it as no longer active.",
        input_model=RetireThemeInput,
        fn=lambda p, ctx: theme_tools.retire_theme(ctx.graph, p, ctx.trace),
        is_mutation=True,
    ),
    # ---- Completion tools ----
    "complete_ingestion": ToolEntry(
        name="complete_ingestion",
        description="Signal completion of an ingestion run. Provide a natural language summary of what was ingested and changed.",
        input_model=CompleteIngestionInput,
        fn=lambda p, ctx: completion_tools.complete_ingestion(p, ctx.trace),
        is_completion=True,
    ),
    "deliver_response": ToolEntry(
        name="deliver_response",
        description="Deliver the final answer to the user with cited sources and the node ids consulted during retrieval.",
        input_model=DeliverResponseInput,
        fn=lambda p, ctx: completion_tools.deliver_response(p, ctx.trace),
        is_completion=True,
    ),
    "complete_theme_update": ToolEntry(
        name="complete_theme_update",
        description="Signal completion of a theme update run. List updated themes and provide the full priority order of all active themes.",
        input_model=CompleteThemeUpdateInput,
        fn=lambda p, ctx: completion_tools.complete_theme_update(p, ctx.trace),
        is_completion=True,
    ),
}

# ---- Allowed tool sets per mode ----

GRAPH_READ_TOOLS = [
    "search_graph",
    "get_node",
    "get_node_neighborhood",
    "get_cold_logs",
    "list_transcripts",
    "get_transcript_span",
    "list_chats",
    "get_chat",
]

GRAPH_WRITE_TOOLS = [
    "create_node",
    "update_node",
    "delete_node",
    "create_edge",
    "update_edge",
    "delete_edge",
]

INGESTION_TOOLS: list[str] = GRAPH_READ_TOOLS + GRAPH_WRITE_TOOLS + ["complete_ingestion"]

QUERY_TOOLS: list[str] = GRAPH_READ_TOOLS + GRAPH_WRITE_TOOLS + ["get_theme", "deliver_response"]

THEME_MODE_TOOLS: list[str] = (
    ["search_graph", "get_node", "get_node_neighborhood", "get_cold_logs"]
    + ["get_theme", "create_theme", "update_theme", "retire_theme"]
    + ["complete_theme_update"]
)


def get_tool_definitions(allowed_tools: list[str]) -> list[dict]:
    """Return LiteLLM-compatible tool definitions for the given tool names."""
    return [
        {
            "type": "function",
            "function": {
                "name": REGISTRY[name].name,
                "description": REGISTRY[name].description,
                "parameters": REGISTRY[name].input_model.model_json_schema(),
            },
        }
        for name in allowed_tools
        if name in REGISTRY
    ]
