from __future__ import annotations

from datetime import datetime

from falkordb import Graph

from weavy.application.contracts import (
    GetNodeOutput,
    OperationResult,
    SearchGraphOutput,
)
from weavy.models.graph import ProvenanceInput
from weavy.models.traces import RunTrace, TouchedEdge, TouchedNode
from weavy.services import embedding
from weavy.store import graph as store_graph
from weavy.store import system as store_system


def get_node(graph: Graph, *, node_ids: list[str]) -> GetNodeOutput:
    nodes_by_id = store_graph.get_nodes(graph, node_ids)
    results = [nodes_by_id[node_id] for node_id in node_ids if node_id in nodes_by_id]
    not_found = [node_id for node_id in node_ids if node_id not in nodes_by_id]
    return GetNodeOutput(results=results, not_found=not_found)


def search_graph(
    graph: Graph,
    *,
    query: str,
    limit: int = 10,
    time_range: list[datetime] | None = None,
) -> SearchGraphOutput:
    query_embedding = embedding.embed(query)
    return store_graph.search_graph(
        graph,
        query=query,
        limit=limit,
        query_embedding=query_embedding,
        time_range=time_range,
    )


def create_node(
    graph: Graph,
    *,
    aliases: list[str],
    summary: str,
    note: str,
    provenance: ProvenanceInput,
    trace: RunTrace,
    event_time: datetime | None = None,
    happened_at: datetime | None = None,
    session_id: str | None = None,
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
        event_time=event_time,
        happened_at=happened_at,
    )
    if session_id is not None:
        store_graph.link_mention(graph, session_id, node_id)
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
    event_time: datetime | None = None,
    happened_at: datetime | None = None,
    session_id: str | None = None,
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
        event_time=event_time,
        happened_at=happened_at,
    )
    if session_id is not None:
        store_graph.link_mention(graph, session_id, node_id)
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
    fact: str,
    note: str,
    provenance: ProvenanceInput,
    trace: RunTrace,
    event_time: datetime | None = None,
    happened_at: datetime | None = None,
    source_id: str | None = None,
) -> OperationResult:
    edge_id = store_system.increment_counter(graph, "edge")
    vec = embedding.embed_edge(label, fact)
    result = store_graph.create_edge(
        graph,
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        label=label,
        fact=fact,
        note=note,
        edge_id=edge_id,
        provenance=provenance,
        embedding=vec,
        event_time=event_time,
        happened_at=happened_at,
        source_id=source_id,
    )
    trace.touched_edges.append(TouchedEdge(edge_id=edge_id, action="created"))
    return result


def update_edge(
    graph: Graph,
    *,
    edge_id: str,
    note: str,
    provenance: ProvenanceInput,
    trace: RunTrace,
    new_label: str | None = None,
    new_fact: str | None = None,
    event_time: datetime | None = None,
    happened_at: datetime | None = None,
) -> OperationResult:
    vec: list[float] | None = None
    if new_label is not None or new_fact is not None:
        current = store_graph.get_edge(graph, edge_id)
        label = new_label if new_label is not None else current.label
        fact = new_fact if new_fact is not None else current.fact
        vec = embedding.embed_edge(label, fact)

    result = store_graph.update_edge(
        graph,
        edge_id=edge_id,
        note=note,
        new_label=new_label,
        new_fact=new_fact,
        provenance=provenance,
        embedding=vec,
        event_time=event_time,
        happened_at=happened_at,
    )
    trace.touched_edges.append(TouchedEdge(edge_id=edge_id, action="updated"))
    return result


def delete_edge(graph: Graph, *, edge_id: str, trace: RunTrace) -> OperationResult:
    result = store_graph.delete_edge(graph, edge_id)
    trace.touched_edges.append(TouchedEdge(edge_id=edge_id, action="deleted"))
    return result
