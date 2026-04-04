"""
Read tools — graph and source retrieval. Implemented in Phase 3 (graph) and Phase 2 (sources).
All functions are importable and fully typed; bodies raise NotImplementedError until implemented.
"""

from falkordb import Graph

from arakne.models.tools import (
    GetChatInput,
    GetChatOutput,
    GetColdLogsInput,
    GetColdLogsOutput,
    GetNodeInput,
    GetNodeNeighborhoodInput,
    GetNodeNeighborhoodOutput,
    GetNodeOutput,
    GetThemeInput,
    GetThemeOutput,
    GetTranscriptSpanInput,
    GetTranscriptSpanOutput,
    ListChatsInput,
    ListChatsOutput,
    ListTranscriptsInput,
    ListTranscriptsOutput,
    SearchGraphInput,
    SearchGraphOutput,
)
from arakne.store import canonical as store_canonical
from arakne.store import graph as store_graph
from arakne.store import themes as store_themes


def search_graph(graph: Graph, params: SearchGraphInput) -> SearchGraphOutput:
    return store_graph.search_graph(graph, params)


def get_node_neighborhood(
    graph: Graph, params: GetNodeNeighborhoodInput
) -> GetNodeNeighborhoodOutput:
    return store_graph.get_node_neighborhood(graph, params.node_id, params.depth)


def get_node(graph: Graph, params: GetNodeInput) -> GetNodeOutput:
    return store_graph.get_node(graph, params.node_id)


def get_cold_logs(graph: Graph, params: GetColdLogsInput) -> GetColdLogsOutput:
    return store_graph.get_cold_logs(graph, params.node_id)


def list_transcripts(graph: Graph, params: ListTranscriptsInput) -> ListTranscriptsOutput:
    return store_canonical.list_transcripts(graph, params)


def get_transcript_span(
    graph: Graph, params: GetTranscriptSpanInput
) -> GetTranscriptSpanOutput:
    return store_canonical.get_transcript_span(
        graph, params.transcript_id, params.start_offset, params.end_offset
    )


def list_chats(graph: Graph, params: ListChatsInput) -> ListChatsOutput:
    return store_canonical.list_chats(graph, params)


def get_chat(graph: Graph, params: GetChatInput) -> GetChatOutput:
    return store_canonical.get_chat(
        graph, params.chat_id, params.start_index, params.end_index
    )


def get_theme(graph: Graph, params: GetThemeInput) -> GetThemeOutput:
    return store_themes.get_theme(graph, params.name)
