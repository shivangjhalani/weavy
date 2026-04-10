from __future__ import annotations

from falkordb import Graph

from weavy.application.contracts import GetNodeOutput, OperationResult, SearchGraphOutput
from weavy.models.graph import ProvenanceInput
from weavy.models.traces import RunTrace, TouchedEdge, TouchedNode
from weavy.services import embedding
from weavy.store import graph as store_graph
from weavy.store import system as store_system


def get_node(graph: Graph, *, node_ids: list[str]) -> GetNodeOutput:
    nodes_by_id = store_graph.get_nodes(graph, node_ids)
    results = [
        nodes_by_id[node_id] for node_id in node_ids if node_id in nodes_by_id
    ]
    not_found = [node_id for node_id in node_ids if node_id not in nodes_by_id]
    return GetNodeOutput(results=results, not_found=not_found)


def search_graph(graph: Graph, *, query: str, limit: int = 10) -> SearchGraphOutput:
    query_embedding = embedding.embed(query)
    return store_graph.search_graph(
        graph, query=query, limit=limit, query_embedding=query_embedding
    )


def create_node(
    graph: Graph,
    *,
    aliases: list[str],
    summary: str,
    note: str,
    provenance: ProvenanceInput,
    trace: RunTrace,
) -> OperationResult:
    node_id = store_system.increment_counter(graph, "node")
    vec = embedding.embed_node(aliases, summary)
    result = store_graph.create_node(
        graph,
        aliases=aliases,
        summary=summary,
        note=note,
        provenance=provenance,
        node_id=node_id,
        embedding=vec,
    )
    trace.touched_nodes.append(TouchedNode(node_id=node_id, action="created"))
    return result


def update_node(
    graph: Graph,
    *,
    node_id: str,
    note: str,
    provenance: ProvenanceInput,
    trace: RunTrace,
    new_summary: str | None = None,
    new_aliases: list[str] | None = None,
) -> OperationResult:
    vec: list[float] | None = None
    fetched_summary: str | None = None
    if new_summary is not None or new_aliases is not None:
        current = store_graph.get_node(graph, node_id)
        fetched_summary = current.node.summary
        aliases = new_aliases if new_aliases is not None else current.node.aliases
        summary = new_summary if new_summary is not None else fetched_summary
        vec = embedding.embed_node(aliases, summary)

    result = store_graph.update_node(
        graph,
        node_id=node_id,
        note=note,
        new_summary=new_summary,
        new_aliases=new_aliases,
        provenance=provenance,
        embedding=vec,
        current_summary=fetched_summary,
    )
    trace.touched_nodes.append(TouchedNode(node_id=node_id, action="updated"))
    return result


def delete_node(graph: Graph, *, node_id: str, trace: RunTrace) -> OperationResult:
    result = store_graph.delete_node(graph, node_id)
    trace.touched_nodes.append(TouchedNode(node_id=node_id, action="deleted"))
    return result


def create_edge(
    graph: Graph,
    *,
    from_node_id: str,
    to_node_id: str,
    label: str,
    note: str,
    trace: RunTrace,
) -> OperationResult:
    edge_id = store_system.increment_counter(graph, "edge")
    result = store_graph.create_edge(
        graph,
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        label=label,
        note=note,
        edge_id=edge_id,
    )
    trace.touched_edges.append(TouchedEdge(edge_id=edge_id, action="created"))
    return result


def update_edge(
    graph: Graph, *, edge_id: str, new_label: str, trace: RunTrace
) -> OperationResult:
    result = store_graph.update_edge(graph, edge_id, new_label)
    trace.touched_edges.append(TouchedEdge(edge_id=edge_id, action="updated"))
    return result


def delete_edge(graph: Graph, *, edge_id: str, trace: RunTrace) -> OperationResult:
    result = store_graph.delete_edge(graph, edge_id)
    trace.touched_edges.append(TouchedEdge(edge_id=edge_id, action="deleted"))
    return result
