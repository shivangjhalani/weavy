"""
Write tools — semantic graph CRUD with provenance validation.
"""

from falkordb import Graph

from weavy.models.graph import ProvenanceInput
from weavy.models.tools import (
    CreateEdgeInput,
    CreateNodeInput,
    DeleteEdgeInput,
    DeleteNodeInput,
    OperationResult,
    UpdateEdgeInput,
    UpdateNodeInput,
)
from weavy.models.traces import (
    EdgeSnapshot,
    MutationOp,
    NodeSnapshot,
    RunTrace,
    TouchedEdge,
    TouchedNode,
)
from weavy.store import graph as store_graph
from weavy.store import system as store_system


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


def _snapshot_node(graph: Graph, node_id: str, include_edges: bool = False) -> NodeSnapshot | None:
    """Fetch a node's current state as a snapshot for rollback. Returns None if not found."""
    result = graph.query(
        "MATCH (n:SemanticNode {id: $id}) RETURN n",
        {"id": node_id},
    )
    if not result.result_set:
        return None
    props = result.result_set[0][0].properties

    edges: list[EdgeSnapshot] = []
    if include_edges:
        edge_result = graph.query(
            """
            MATCH (a:SemanticNode)-[r:RELATES]->(b:SemanticNode)
            WHERE a.id = $id OR b.id = $id
            RETURN r.id, r.label, a.id, b.id
            """,
            {"id": node_id},
        )
        for row in edge_result.result_set:
            edges.append(EdgeSnapshot(
                id=row[0],
                label=row[1],
                from_node_id=row[2],
                to_node_id=row[3],
            ))

    return NodeSnapshot(
        id=props["id"],
        name=props.get("name", ""),
        aliases=props.get("aliases") or [],
        summary=props.get("summary", ""),
        log=props.get("log") or [],
        total_log_count=props.get("total_log_count", 0),
        edges=edges,
    )


def _snapshot_edge(graph: Graph, edge_id: str) -> EdgeSnapshot | None:
    """Fetch an edge's current state as a snapshot for rollback. Returns None if not found."""
    result = graph.query(
        """
        MATCH (a:SemanticNode)-[r:RELATES {id: $id}]->(b:SemanticNode)
        RETURN r.id, r.label, a.id, b.id
        """,
        {"id": edge_id},
    )
    if not result.result_set:
        return None
    row = result.result_set[0]
    return EdgeSnapshot(
        id=row[0],
        label=row[1],
        from_node_id=row[2],
        to_node_id=row[3],
    )


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
    trace.mutation_ops.append(MutationOp(op="create_node", node_id=node_id))
    return result


def update_node(
    graph: Graph, params: UpdateNodeInput, trace: RunTrace
) -> OperationResult:
    _validate_node_provenance(params.provenance, trace.mode)
    before = _snapshot_node(graph, params.node_id)
    result = store_graph.update_node(
        graph,
        node_id=params.node_id,
        note=params.note,
        new_summary=params.new_summary,
        new_aliases=params.new_aliases,
        provenance=params.provenance,
    )
    trace.touched_nodes.append(TouchedNode(node_id=params.node_id, action="updated"))
    trace.mutation_ops.append(MutationOp(op="update_node", node_id=params.node_id, node_before=before))
    return result


def delete_node(
    graph: Graph, params: DeleteNodeInput, trace: RunTrace
) -> OperationResult:
    before = _snapshot_node(graph, params.node_id, include_edges=True)
    result = store_graph.delete_node(graph, node_id=params.node_id, reason=params.reason)
    trace.touched_nodes.append(TouchedNode(node_id=params.node_id, action="deleted"))
    trace.mutation_ops.append(MutationOp(op="delete_node", node_id=params.node_id, node_before=before))
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
    trace.mutation_ops.append(MutationOp(op="create_edge", edge_id=edge_id))
    return result


def update_edge(
    graph: Graph, params: UpdateEdgeInput, trace: RunTrace
) -> OperationResult:
    before = _snapshot_edge(graph, params.edge_id)
    result = store_graph.update_edge(graph, edge_id=params.edge_id, new_label=params.new_label)
    trace.touched_edges.append(TouchedEdge(edge_id=params.edge_id, action="updated"))
    trace.mutation_ops.append(MutationOp(op="update_edge", edge_id=params.edge_id, edge_before=before))
    return result


def delete_edge(
    graph: Graph, params: DeleteEdgeInput, trace: RunTrace
) -> OperationResult:
    before = _snapshot_edge(graph, params.edge_id)
    result = store_graph.delete_edge(graph, edge_id=params.edge_id, reason=params.reason)
    trace.touched_edges.append(TouchedEdge(edge_id=params.edge_id, action="deleted"))
    trace.mutation_ops.append(MutationOp(op="delete_edge", edge_id=params.edge_id, edge_before=before))
    return result
