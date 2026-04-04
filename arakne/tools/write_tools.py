"""
Write tools — semantic graph CRUD with provenance validation.
"""

from falkordb import Graph

from arakne.models.graph import ProvenanceInput
from arakne.models.tools import (
    CreateEdgeInput,
    CreateNodeInput,
    DeleteEdgeInput,
    DeleteNodeInput,
    OperationResult,
    UpdateEdgeInput,
    UpdateNodeInput,
)
from arakne.models.traces import RunTrace, TouchedEdge, TouchedNode
from arakne.store import graph as store_graph
from arakne.store import system as store_system


def _validate_node_provenance(provenance: ProvenanceInput | None, mode: str) -> None:
    """Enforce provenance rules by agent mode. Raises ValueError on violation."""
    if mode == "ingestion":
        if provenance is None:
            raise ValueError("Ingestion writes require provenance (rec:N with offsets).")
        if not provenance.source_id.startswith("rec:"):
            raise ValueError(
                f"Ingestion provenance must use rec:N source_id, got '{provenance.source_id}'."
            )
        if provenance.end_offset is None:
            raise ValueError("Ingestion provenance requires end_offset (seconds into recording).")
    elif mode == "query":
        if provenance is None:
            raise ValueError("Chat writes require provenance (chat:N with message_index).")
        if not provenance.source_id.startswith("chat:"):
            raise ValueError(
                f"Chat provenance must use chat:N source_id, got '{provenance.source_id}'."
            )
        if provenance.end_offset is not None:
            raise ValueError("Chat provenance end_offset must be None (use start_offset for message_index).")
    elif mode == "theme":
        raise ValueError(
            "Theme mode must not write to SemanticNodes directly. "
            "Use theme tools (create_theme, update_theme, retire_theme) instead."
        )
    else:
        raise ValueError(f"Unknown mode '{mode}'.")


def create_node(
    graph: Graph, params: CreateNodeInput, trace: RunTrace
) -> OperationResult:
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


def update_node(
    graph: Graph, params: UpdateNodeInput, trace: RunTrace
) -> OperationResult:
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


def delete_node(
    graph: Graph, params: DeleteNodeInput, trace: RunTrace
) -> OperationResult:
    result = store_graph.delete_node(graph, node_id=params.node_id, reason=params.reason)
    trace.touched_nodes.append(TouchedNode(node_id=params.node_id, action="deleted"))
    return result


def create_edge(
    graph: Graph, params: CreateEdgeInput, trace: RunTrace
) -> OperationResult:
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


def update_edge(
    graph: Graph, params: UpdateEdgeInput, trace: RunTrace
) -> OperationResult:
    result = store_graph.update_edge(graph, edge_id=params.edge_id, new_label=params.new_label)
    trace.touched_edges.append(TouchedEdge(edge_id=params.edge_id, action="updated"))
    return result


def delete_edge(
    graph: Graph, params: DeleteEdgeInput, trace: RunTrace
) -> OperationResult:
    result = store_graph.delete_edge(graph, edge_id=params.edge_id, reason=params.reason)
    trace.touched_edges.append(TouchedEdge(edge_id=params.edge_id, action="deleted"))
    return result
