from __future__ import annotations

from falkordb import Graph

from weavy.models.graph import ProvenanceInput
from weavy.models.tools import (
    CreateEdgeInput,
    CreateNodeInput,
    DeleteEdgeInput,
    DeleteNodeInput,
    GetNodeInput,
    GetNodeOutput,
    GetTranscriptSpanInput,
    GetTranscriptSpanOutput,
    GetTranscriptSpanResult,
    OperationResult,
    UpdateEdgeInput,
    UpdateNodeInput,
)
from weavy.models.traces import RunTrace, TouchedEdge, TouchedNode
from weavy.store import canonical as store_canonical
from weavy.store import graph as store_graph
from weavy.store import system as store_system


def get_node(graph: Graph, params: GetNodeInput) -> GetNodeOutput:
    results = []
    not_found: list[str] = []
    for node_id in params.node_ids:
        try:
            results.append(store_graph.get_node(graph, node_id))
        except ValueError:
            not_found.append(node_id)
    return GetNodeOutput(results=results, not_found=not_found)


def get_transcript_span(
    graph: Graph, params: GetTranscriptSpanInput
) -> GetTranscriptSpanOutput:
    # Group by transcript_id to avoid fetching the same transcript multiple times
    by_id: dict[str, list] = {}
    for span in params.spans:
        by_id.setdefault(span.transcript_id, []).append(span)

    results: list[GetTranscriptSpanResult] = []
    for tid, spans in by_id.items():
        transcript = store_canonical.get_transcript(graph, tid)
        for span in spans:
            text = store_canonical._extract_span(transcript.text, span.start_offset, span.end_offset)
            results.append(GetTranscriptSpanResult(transcript_id=tid, text=text))
    return GetTranscriptSpanOutput(results=results)


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
