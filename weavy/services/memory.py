from __future__ import annotations

from falkordb import Graph

from weavy.models.graph import ProvenanceInput
from weavy.models.tools import (
    CreateEdgeInput,
    CreateNodeInput,
    CreateThemeInput,
    DeleteEdgeInput,
    DeleteNodeInput,
    GetChatInput,
    GetChatOutput,
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
    OperationResult,
    RetireThemeInput,
    SearchGraphInput,
    SearchGraphOutput,
    UpdateEdgeInput,
    UpdateNodeInput,
    UpdateThemeInput,
)
from weavy.models.traces import RunTrace, TouchedEdge, TouchedNode
from weavy.store import canonical as store_canonical
from weavy.store import graph as store_graph
from weavy.store import system as store_system
from weavy.store import themes as store_themes


def search_graph(graph: Graph, params: SearchGraphInput) -> SearchGraphOutput:
    return store_graph.search_graph(graph, params)


def get_node(graph: Graph, params: GetNodeInput) -> GetNodeOutput:
    results = []
    not_found: list[str] = []
    for node_id in params.node_ids:
        try:
            results.append(store_graph.get_node(graph, node_id))
        except ValueError:
            not_found.append(node_id)
    return GetNodeOutput(results=results, not_found=not_found)


def get_node_neighborhood(
    graph: Graph, params: GetNodeNeighborhoodInput
) -> GetNodeNeighborhoodOutput:
    return store_graph.get_node_neighborhood(graph, params.node_id)


def list_transcripts(graph: Graph, params: ListTranscriptsInput) -> ListTranscriptsOutput:
    return store_canonical.list_transcripts(graph, params)


def get_transcript_span(
    graph: Graph, params: GetTranscriptSpanInput
) -> GetTranscriptSpanOutput:
    results: list[GetTranscriptSpanResult] = [
        store_canonical.get_transcript_span(graph, span.transcript_id, span.start_offset, span.end_offset)
        for span in params.spans
    ]
    return GetTranscriptSpanOutput(results=results)


def list_chats(graph: Graph, params: ListChatsInput) -> ListChatsOutput:
    return store_canonical.list_chats(graph, params)


def get_chat(graph: Graph, params: GetChatInput) -> GetChatOutput:
    return store_canonical.get_chat(graph, params.chat_id, params.start_index, params.end_index)


def get_theme(graph: Graph, params: GetThemeInput) -> GetThemeOutput:
    return store_themes.get_theme(graph, params.name)


def _validate_node_provenance(provenance: ProvenanceInput | None, mode: str) -> None:
    if mode == "ingestion":
        if provenance is None:
            raise ValueError("Ingestion writes require provenance.")
        if not provenance.source_id.startswith("rec:"):
            raise ValueError("Ingestion provenance must use rec:N.")
        if provenance.end_offset is None:
            raise ValueError("Ingestion provenance requires end_offset.")
        return

    if mode == "query":
        if provenance is None:
            raise ValueError("Query writes require provenance.")
        if not provenance.source_id.startswith("chat:"):
            raise ValueError("Query provenance must use chat:N.")
        if provenance.end_offset is not None:
            raise ValueError("Query provenance end_offset must be None.")
        return

    raise ValueError("Theme mode cannot write semantic nodes.")


def create_node(graph: Graph, params: CreateNodeInput, trace: RunTrace) -> OperationResult:
    _validate_node_provenance(params.provenance, trace.mode)
    node_id = store_system.increment_counter(graph, "node")
    result = store_graph.create_node(
        graph,
        aliases=params.aliases,
        summary=params.summary,
        note=params.note,
        provenance=params.provenance,
        node_id=node_id,
    )
    trace.touched_nodes.append(TouchedNode(node_id=node_id, action="created"))
    return result


def update_node(graph: Graph, params: UpdateNodeInput, trace: RunTrace) -> OperationResult:
    _validate_node_provenance(params.provenance, trace.mode)
    result = store_graph.update_node(
        graph,
        node_id=params.node_id,
        note=params.note,
        new_summary=params.new_summary,
        new_aliases=params.new_aliases,
        provenance=params.provenance,
    )
    trace.touched_nodes.append(TouchedNode(node_id=params.node_id, action="updated"))
    return result


def delete_node(graph: Graph, params: DeleteNodeInput, trace: RunTrace) -> OperationResult:
    result = store_graph.delete_node(graph, params.node_id, params.reason)
    trace.touched_nodes.append(TouchedNode(node_id=params.node_id, action="deleted"))
    return result


def create_edge(graph: Graph, params: CreateEdgeInput, trace: RunTrace) -> OperationResult:
    edge_id = store_system.increment_counter(graph, "edge")
    result = store_graph.create_edge(
        graph,
        from_node_id=params.from_node_id,
        to_node_id=params.to_node_id,
        label=params.label,
        edge_id=edge_id,
    )
    trace.touched_edges.append(TouchedEdge(edge_id=edge_id, action="created"))
    return result


def update_edge(graph: Graph, params: UpdateEdgeInput, trace: RunTrace) -> OperationResult:
    result = store_graph.update_edge(graph, params.edge_id, params.new_label)
    trace.touched_edges.append(TouchedEdge(edge_id=params.edge_id, action="updated"))
    return result


def delete_edge(graph: Graph, params: DeleteEdgeInput, trace: RunTrace) -> OperationResult:
    result = store_graph.delete_edge(graph, params.edge_id, params.reason)
    trace.touched_edges.append(TouchedEdge(edge_id=params.edge_id, action="deleted"))
    return result


def create_theme(graph: Graph, params: CreateThemeInput) -> OperationResult:
    return store_themes.create_theme(graph, params.name, params.state, params.anchors, params.status)


def update_theme(graph: Graph, params: UpdateThemeInput) -> OperationResult:
    return store_themes.update_theme(
        graph,
        params.name,
        params.new_state,
        params.new_anchors,
        params.new_status,
    )


def retire_theme(graph: Graph, params: RetireThemeInput) -> OperationResult:
    return store_themes.retire_theme(graph, params.name)
