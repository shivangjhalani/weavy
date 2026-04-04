"""
Read tools — graph and source retrieval.
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
    GetTranscriptSpanResult,
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
    return store_graph.get_node_neighborhood(graph, params.node_id)


def get_node(graph: Graph, params: GetNodeInput) -> GetNodeOutput:
    results = []
    not_found: list[str] = []
    for nid in params.node_ids:
        try:
            results.append(store_graph.get_node(graph, nid))
        except ValueError:
            not_found.append(nid)
    return GetNodeOutput(results=results, not_found=not_found)


def get_cold_logs(graph: Graph, params: GetColdLogsInput) -> GetColdLogsOutput:
    return store_graph.get_cold_logs(graph, params.node_id)


def list_transcripts(graph: Graph, params: ListTranscriptsInput) -> ListTranscriptsOutput:
    return store_canonical.list_transcripts(graph, params)


def get_transcript_span(
    graph: Graph, params: GetTranscriptSpanInput
) -> GetTranscriptSpanOutput:
    results: list[GetTranscriptSpanResult] = [
        store_canonical.get_transcript_span(graph, s.transcript_id, s.start_offset, s.end_offset)
        for s in params.spans
    ]
    return GetTranscriptSpanOutput(results=results)


def list_chats(graph: Graph, params: ListChatsInput) -> ListChatsOutput:
    return store_canonical.list_chats(graph, params)


def get_chat(graph: Graph, params: GetChatInput) -> GetChatOutput:
    return store_canonical.get_chat(
        graph, params.chat_id, params.start_index, params.end_index
    )


def get_theme(graph: Graph, params: GetThemeInput) -> GetThemeOutput:
    return store_themes.get_theme(graph, params.name)
