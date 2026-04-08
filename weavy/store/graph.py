"""
Semantic graph CRUD — SemanticNode and SemanticEdge operations in FalkorDB.
Implemented in Phase 3.
"""

import json
from datetime import datetime, timezone

import litellm
from falkordb import Graph

from weavy.config import settings
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


def generate_embedding(aliases: list[str], summary: str) -> list[float]:
    text = summary + " " + " ".join(aliases)
    response = litellm.embedding(model=settings.GEMINI_EMBEDDING_MODEL, input=[text])
    return response.data[0]["embedding"]


# ---------------------------------------------------------------------------
# Node CRUD
# ---------------------------------------------------------------------------


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
    embedding = generate_embedding(aliases, summary)
    graph.query(
        "MATCH (n:SemanticNode {id: $id}) SET n.embedding = vecf32($embedding)",
        {"id": node_id, "embedding": embedding},
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
    result = graph.query(
        "MATCH (n:SemanticNode {id: $id}) RETURN n",
        {"id": node_id},
    )
    if not result.result_set:
        raise ValueError(f"SemanticNode '{node_id}' not found.")

    props = result.result_set[0][0].properties
    current_summary = props["summary"]

    # Archive old summary into note if a new summary is being written
    effective_note = note
    if new_summary is not None:
        effective_note = f"[archived summary] {current_summary} | Agent note: {note}"

    entry = _make_log_entry(provenance, effective_note)
    entry_json = _serialize_log_entry(entry)

    # Build SET clauses dynamically
    set_parts = [
        "n.log = n.log + [$entry_json]",
        "n.total_log_count = n.total_log_count + 1",
    ]
    params: dict = {"id": node_id, "entry_json": entry_json}

    if new_summary is not None:
        set_parts.append("n.summary = $new_summary")
        params["new_summary"] = new_summary
    if new_aliases is not None:
        set_parts.append("n.aliases = $new_aliases")
        set_parts.append("n.name = $new_name")
        params["new_aliases"] = new_aliases
        params["new_name"] = new_aliases[0]

    graph.query(
        f"MATCH (n:SemanticNode {{id: $id}}) SET {', '.join(set_parts)}",
        params,
    )

    if new_summary is not None or new_aliases is not None:
        effective_aliases = new_aliases if new_aliases is not None else props.get("aliases", [])
        effective_summary = new_summary if new_summary is not None else current_summary
        embedding = generate_embedding(effective_aliases, effective_summary)
        graph.query(
            "MATCH (n:SemanticNode {id: $id}) SET n.embedding = vecf32($embedding)",
            {"id": node_id, "embedding": embedding},
        )
    return OperationResult(ok=True, id=node_id)


def delete_node(graph: Graph, node_id: str, reason: str) -> OperationResult:  # noqa: ARG001
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


def delete_edge(graph: Graph, edge_id: str, reason: str) -> OperationResult:  # noqa: ARG001
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
    fetch_k = params.limit * 2

    # --- Keyword pass ---
    kw_result = graph.query(
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
        {"query": params.query, "limit": fetch_k},
    )
    keyword_hits: dict[str, tuple] = {}
    for row in kw_result.result_set:
        keyword_hits[row[0]] = (row[1], row[2], int(row[3]))

    # --- Vector pass ---
    vec_hits: dict[str, tuple] = {}
    query_vec = generate_embedding([], params.query)
    vec_result = graph.query(
        """
        CALL db.idx.vector.queryNodes('SemanticNode', 'embedding', $k, vecf32($vec))
        YIELD node, score
        OPTIONAL MATCH (node)-[r:RELATES]-()
        WITH node, score, count(r) AS edge_count
        RETURN node.id, node.aliases, node.summary, edge_count, score
        """,
        {"k": fetch_k, "vec": query_vec},
    )
    for row in vec_result.result_set:
        vec_hits[row[0]] = (row[1], row[2], int(row[3]), float(row[4]))

    # --- Fusion ---
    # Score: vec + keyword = vec_score + 0.5, vec-only = vec_score, keyword-only = 0.4
    candidates: dict[str, dict] = {}
    for nid, (aliases, summary, edge_count, vec_score) in vec_hits.items():
        combined = vec_score + (0.5 if nid in keyword_hits else 0.0)
        candidates[nid] = {
            "aliases": aliases,
            "summary": summary,
            "edge_count": edge_count,
            "score": combined,
        }
    for nid, (aliases, summary, edge_count) in keyword_hits.items():
        if nid not in candidates:
            candidates[nid] = {
                "aliases": aliases,
                "summary": summary,
                "edge_count": edge_count,
                "score": 0.4,
            }

    ranked = sorted(candidates.items(), key=lambda x: x[1]["score"], reverse=True)

    results = []
    for nid, item in ranked[: params.limit]:
        aliases = item["aliases"]
        summary = item["summary"]
        results.append(
            SearchResult(
                id=nid,
                canonical_alias=aliases[0] if aliases else nid,
                summary_line=summary.splitlines()[0] if summary else "",
                edge_count=item["edge_count"],
            )
        )
    return SearchGraphOutput(results=results)


def get_node(graph: Graph, node_id: str) -> GetNodeResult:
    # Fetch node properties and outgoing edges in one query
    result = graph.query(
        """
        MATCH (n:SemanticNode {id: $id})
        OPTIONAL MATCH (n)-[r:RELATES]->(m:SemanticNode)
        RETURN n, collect(CASE WHEN r IS NOT NULL THEN [r.id, r.label, m.id] ELSE null END) AS edges
        """,
        {"id": node_id},
    )
    if not result.result_set:
        raise ValueError(f"SemanticNode '{node_id}' not found.")

    row = result.result_set[0]
    node_props = row[0].properties
    raw_edges = row[1] or []

    all_entries = [_deserialize_log_entry(s) for s in (node_props.get("log") or [])]

    node = SemanticNode(
        id=node_props["id"],
        aliases=node_props.get("aliases") or [],
        summary=node_props["summary"],
        embedding=None,
        total_log_count=node_props.get("total_log_count", 0),
        log=all_entries,
    )

    # Build edge list (skip null placeholders from COLLECT when no edges exist)
    edges = []
    for edge_data in raw_edges:
        if edge_data is None:
            continue
        edge_id, label, to_id = edge_data
        if edge_id is not None:
            edges.append(SemanticEdge(id=edge_id, from_node_id=node_id, to_node_id=to_id, label=label))

    return GetNodeResult(node=node, edges=edges)


def get_node_neighborhood(
    graph: Graph, node_id: str
) -> GetNodeNeighborhoodOutput:
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

    all_entries = [_deserialize_log_entry(s) for s in (node_props.get("log") or [])]
    orientation_log = all_entries[-2:] if all_entries else []

    node = SemanticNode(
        id=node_props["id"],
        aliases=node_props.get("aliases") or [],
        summary=node_props["summary"],
        embedding=None,
        total_log_count=node_props.get("total_log_count", 0),
        log=orientation_log,
    )

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
