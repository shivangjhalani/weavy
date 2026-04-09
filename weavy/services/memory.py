from __future__ import annotations

from falkordb import Graph

from weavy.models.tools import (
    CreateEdgeInput,
    CreateNodeInput,
    DeleteEdgeInput,
    DeleteNodeInput,
    GetNodeInput,
    GetNodeOutput,
    OperationResult,
    SearchGraphInput,
    SearchGraphOutput,
    UpdateEdgeInput,
    UpdateNodeInput,
)
from weavy.models.traces import RunTrace, TouchedEdge, TouchedNode
from weavy.services import embedding
from weavy.store import graph as store_graph
from weavy.store import system as store_system


def get_node(graph: Graph, params: GetNodeInput) -> GetNodeOutput:
    nodes_by_id = store_graph.get_nodes(graph, params.node_ids)
    results = [
        nodes_by_id[node_id] for node_id in params.node_ids if node_id in nodes_by_id
    ]
    not_found = [node_id for node_id in params.node_ids if node_id not in nodes_by_id]
    return GetNodeOutput(results=results, not_found=not_found)


def search_graph(graph: Graph, params: SearchGraphInput) -> SearchGraphOutput:
    query_embedding = embedding.embed(params.query)
    return store_graph.search_graph(graph, params, query_embedding)


def create_node(
    graph: Graph, params: CreateNodeInput, trace: RunTrace
) -> OperationResult:
    node_id = store_system.increment_counter(graph, "node")
    vec = embedding.embed_node(params.aliases, params.summary)
    result = store_graph.create_node(
        graph,
        aliases=params.aliases,
        summary=params.summary,
        note=params.note,
        provenance=params.provenance,
        node_id=node_id,
        embedding=vec,
    )
    trace.touched_nodes.append(TouchedNode(node_id=node_id, action="created"))
    return result


def update_node(
    graph: Graph, params: UpdateNodeInput, trace: RunTrace
) -> OperationResult:
    vec: list[float] | None = None
    fetched_summary: str | None = None
    if params.new_summary is not None or params.new_aliases is not None:
        current = store_graph.get_node(graph, params.node_id)
        fetched_summary = current.node.summary
        aliases = (
            params.new_aliases
            if params.new_aliases is not None
            else current.node.aliases
        )
        summary = (
            params.new_summary if params.new_summary is not None else fetched_summary
        )
        vec = embedding.embed_node(aliases, summary)

    result = store_graph.update_node(
        graph,
        node_id=params.node_id,
        note=params.note,
        new_summary=params.new_summary,
        new_aliases=params.new_aliases,
        provenance=params.provenance,
        embedding=vec,
        current_summary=fetched_summary,
    )
    trace.touched_nodes.append(TouchedNode(node_id=params.node_id, action="updated"))
    return result


def delete_node(
    graph: Graph, params: DeleteNodeInput, trace: RunTrace
) -> OperationResult:
    result = store_graph.delete_node(graph, params.node_id)
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
        note=params.note,
        edge_id=edge_id,
    )
    trace.touched_edges.append(TouchedEdge(edge_id=edge_id, action="created"))
    return result


def update_edge(
    graph: Graph, params: UpdateEdgeInput, trace: RunTrace
) -> OperationResult:
    result = store_graph.update_edge(graph, params.edge_id, params.new_label)
    trace.touched_edges.append(TouchedEdge(edge_id=params.edge_id, action="updated"))
    return result


def delete_edge(
    graph: Graph, params: DeleteEdgeInput, trace: RunTrace
) -> OperationResult:
    result = store_graph.delete_edge(graph, params.edge_id)
    trace.touched_edges.append(TouchedEdge(edge_id=params.edge_id, action="deleted"))
    return result
