"""
Semantic graph CRUD — SemanticNode and SemanticEdge operations in FalkorDB.
Implemented in Phase 3.
"""

import json
from datetime import datetime, timezone
from typing import Any

from falkordb import Graph

from weavy.models.graph import LogEntry, ProvenanceInput, SemanticEdge, SemanticNode
from weavy.models.tools import (
    GetNodeNeighborhoodOutput,
    GetNodeResult,
    NeighborSummary,
    OperationResult,
    SearchGraphInput,
    SearchGraphOutput,
    SearchResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_log_entry(entry: LogEntry) -> str:
    return json.dumps(entry.model_dump(mode="python"), default=_json_default)


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _deserialize_log_entry(s: str) -> LogEntry:
    data = json.loads(s)
    return LogEntry(**data)


def _make_log_entry(provenance: ProvenanceInput | None, note: str) -> LogEntry:
    if provenance is None:
        raise ValueError("Log entry requires provenance")
    return LogEntry(
        source_id=provenance.source_id,
        timestamp=datetime.now(tz=timezone.utc),
        start_offset=provenance.start_offset,
        end_offset=provenance.end_offset,
        note=note,
    )


def _node_from_props(
    props: dict[str, Any], log_tail: int | None = None
) -> SemanticNode:
    """Construct a SemanticNode from raw FalkorDB properties."""
    all_entries = [_deserialize_log_entry(s) for s in (props.get("log") or [])]
    log = all_entries[-log_tail:] if log_tail is not None else all_entries
    return SemanticNode(
        id=props["id"],
        aliases=props.get("aliases") or [],
        summary=props["summary"],
        embedding=None,
        total_log_count=props.get("total_log_count", 0),
        log=log,
    )


def _build_outgoing_edges(
    node_id: str,
    raw_edges: list[list[str | None] | None],
) -> list[SemanticEdge]:
    edges: list[SemanticEdge] = []
    for edge_data in raw_edges:
        if edge_data is None:
            continue
        edge_id, label, to_id = edge_data
        if edge_id is None or to_id is None:
            continue
        edges.append(
            SemanticEdge(
                id=edge_id, from_node_id=node_id, to_node_id=to_id, label=label
            )
        )
    return edges


def create_node(
    graph: Graph,
    aliases: list[str],
    summary: str,
    note: str,
    provenance: ProvenanceInput | None,
    node_id: str,
) -> OperationResult:
    entry = _make_log_entry(provenance, note)
    entry_json = _serialize_log_entry(entry)
    graph.query(
        """
        CREATE (n:SemanticNode {
            id: $id,
            name: $name,
            aliases: $aliases,
            summary: $summary,
            total_log_count: 1,
            log: [$entry_json]
        })
        """,
        {
            "id": node_id,
            "name": aliases[0],
            "aliases": aliases,
            "summary": summary,
            "entry_json": entry_json,
        },
    )
    return OperationResult(ok=True, id=node_id)


def update_node(
    graph: Graph,
    node_id: str,
    note: str,
    new_summary: str | None,
    new_aliases: list[str] | None,
    provenance: ProvenanceInput | None,
) -> OperationResult:
    # Only fetch current summary when archiving it (new_summary is being replaced)
    effective_note = note
    if new_summary is not None:
        result = graph.query(
            "MATCH (n:SemanticNode {id: $id}) RETURN n.summary",
            {"id": node_id},
        )
        if not result.result_set:
            raise ValueError(f"SemanticNode '{node_id}' not found.")
        current_summary = result.result_set[0][0]
        effective_note = f"[archived summary] {current_summary} | Agent note: {note}"

    entry = _make_log_entry(provenance, effective_note)
    entry_json = _serialize_log_entry(entry)

    # Build SET clauses dynamically
    set_parts = [
        "n.log = n.log + [$entry_json]",
        "n.total_log_count = n.total_log_count + 1",
    ]
    params: dict[str, Any] = {"id": node_id, "entry_json": entry_json}

    if new_summary is not None:
        set_parts.append("n.summary = $new_summary")
        params["new_summary"] = new_summary
    if new_aliases is not None:
        set_parts.append("n.aliases = $new_aliases")
        set_parts.append("n.name = $new_name")
        params["new_aliases"] = new_aliases
        params["new_name"] = new_aliases[0]

    result = graph.query(
        f"MATCH (n:SemanticNode {{id: $id}}) SET {', '.join(set_parts)} RETURN n",
        params,
    )
    if not result.result_set:
        raise ValueError(f"SemanticNode '{node_id}' not found.")

    return OperationResult(ok=True, id=node_id)


def delete_node(graph: Graph, node_id: str, _reason: str) -> OperationResult:
    result = graph.query(
        "MATCH (n:SemanticNode {id: $id}) DETACH DELETE n RETURN count(n)",
        {"id": node_id},
    )
    deleted = result.result_set[0][0] if result.result_set else 0
    if deleted == 0:
        raise ValueError(f"SemanticNode '{node_id}' not found.")
    return OperationResult(ok=True, id=node_id)


# ---------------------------------------------------------------------------
# Edge CRUD
# ---------------------------------------------------------------------------


def create_edge(
    graph: Graph,
    from_node_id: str,
    to_node_id: str,
    label: str,
    edge_id: str,
) -> OperationResult:
    result = graph.query(
        """
        MATCH (a:SemanticNode {id: $from_id}), (b:SemanticNode {id: $to_id})
        CREATE (a)-[r:RELATES {id: $edge_id, label: $label}]->(b)
        RETURN r
        """,
        {
            "from_id": from_node_id,
            "to_id": to_node_id,
            "edge_id": edge_id,
            "label": label,
        },
    )
    if not result.result_set:
        raise ValueError(
            f"Cannot create edge: one or both nodes not found "
            f"(from='{from_node_id}', to='{to_node_id}')."
        )
    return OperationResult(ok=True, id=edge_id)


def update_edge(graph: Graph, edge_id: str, new_label: str) -> OperationResult:
    result = graph.query(
        "MATCH ()-[r:RELATES {id: $id}]->() SET r.label = $label RETURN r",
        {"id": edge_id, "label": new_label},
    )
    if not result.result_set:
        raise ValueError(f"Edge '{edge_id}' not found.")
    return OperationResult(ok=True, id=edge_id)


def delete_edge(graph: Graph, edge_id: str, _reason: str) -> OperationResult:
    result = graph.query(
        "MATCH ()-[r:RELATES {id: $id}]->() DELETE r RETURN count(r)",
        {"id": edge_id},
    )
    deleted = result.result_set[0][0] if result.result_set else 0
    if deleted == 0:
        raise ValueError(f"Edge '{edge_id}' not found.")
    return OperationResult(ok=True, id=edge_id)


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


def search_graph(graph: Graph, params: SearchGraphInput) -> SearchGraphOutput:
    result = graph.query(
        """
        MATCH (n:SemanticNode)
        WHERE ANY(a IN n.aliases WHERE toLower(a) CONTAINS toLower($query))
           OR toLower(n.summary) CONTAINS toLower($query)
        OPTIONAL MATCH (n)-[r:RELATES]-()
        WITH n, count(r) AS edge_count
        RETURN n.id, n.aliases, n.summary, edge_count
        ORDER BY edge_count DESC
        LIMIT $limit
        """,
        {"query": params.query, "limit": params.limit},
    )
    results = []
    for row in result.result_set:
        node_id, aliases, summary, edge_count = row
        results.append(
            SearchResult(
                id=node_id,
                canonical_alias=aliases[0] if aliases else node_id,
                summary_line=summary.splitlines()[0] if summary else "",
                edge_count=int(edge_count),
            )
        )
    return SearchGraphOutput(results=results)


def get_node(graph: Graph, node_id: str) -> GetNodeResult:
    nodes_by_id = get_nodes(graph, [node_id])
    try:
        return nodes_by_id[node_id]
    except KeyError as exc:
        raise ValueError(f"SemanticNode '{node_id}' not found.") from exc


def get_nodes(graph: Graph, node_ids: list[str]) -> dict[str, GetNodeResult]:
    if not node_ids:
        return {}

    # Fetch node properties and outgoing edges for all requested nodes in one query.
    result = graph.query(
        """
        MATCH (n:SemanticNode)
        WHERE n.id IN $ids
        OPTIONAL MATCH (n)-[r:RELATES]->(m:SemanticNode)
        WITH n, collect(CASE WHEN r IS NOT NULL THEN [r.id, r.label, m.id] ELSE null END) AS edges
        RETURN n.id, n, edges
        """,
        {"ids": node_ids},
    )

    nodes_by_id: dict[str, GetNodeResult] = {}
    for found_node_id, raw_node, raw_edges in result.result_set:
        node_props = raw_node.properties
        nodes_by_id[found_node_id] = GetNodeResult(
            node=_node_from_props(node_props),
            edges=_build_outgoing_edges(found_node_id, raw_edges or []),
        )
    return nodes_by_id


def get_node_neighborhood(graph: Graph, node_id: str) -> GetNodeNeighborhoodOutput:
    result = graph.query(
        """
        MATCH (n:SemanticNode {id: $id})
        OPTIONAL MATCH (n)-[r:RELATES]-(m:SemanticNode)
        RETURN n, collect(CASE WHEN r IS NOT NULL THEN [r.id, r.label, m.id, m.aliases, m.summary] ELSE null END) AS neighbor_data
        """,
        {"id": node_id},
    )
    if not result.result_set:
        raise ValueError(f"SemanticNode '{node_id}' not found.")

    row = result.result_set[0]
    node_props = row[0].properties
    raw_neighbors = row[1] or []

    node = _node_from_props(node_props, log_tail=2)

    neighbors = []
    seen_edge_ids = set()
    for nd in raw_neighbors:
        if nd is None:
            continue
        edge_id, edge_label, neighbor_id, neighbor_aliases, neighbor_summary = nd
        if edge_id is None or edge_id in seen_edge_ids:
            continue
        seen_edge_ids.add(edge_id)
        canonical = neighbor_aliases[0] if neighbor_aliases else neighbor_id
        summary_line = neighbor_summary.splitlines()[0] if neighbor_summary else ""
        neighbors.append(
            NeighborSummary(
                edge_id=edge_id,
                edge_label=edge_label,
                node_id=neighbor_id,
                canonical_alias=canonical,
                summary_line=summary_line,
            )
        )

    return GetNodeNeighborhoodOutput(node=node, neighbors=neighbors)
