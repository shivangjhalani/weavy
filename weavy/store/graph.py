"""
Semantic graph CRUD — SemanticNode and SemanticEdge operations in FalkorDB.
Implemented in Phase 3.
"""

import json
from datetime import datetime, timezone
from typing import Any

from falkordb import Graph

from weavy.application.contracts import (
    GetNodeNeighborhoodOutput,
    GetNodeResult,
    NeighborSummary,
    OperationResult,
    SearchGraphOutput,
    SearchResult,
)
from weavy.models.graph import LogEntry, ProvenanceInput, SemanticEdge, SemanticNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _vecf32_literal(vec: list[float]) -> str:
    """Format a Python float list as a FalkorDB vecf32() Cypher literal.

    FalkorDB's vecf32() requires an inline array literal — it cannot accept
    parameterized values via $variable. All official docs use f-string
    interpolation. This helper centralizes validation and formatting.
    """
    import math

    for i, v in enumerate(vec):
        if not isinstance(v, (int, float)):
            raise ValueError(
                f"Embedding element {i} is {type(v).__name__}, expected float"
            )
        if math.isnan(v) or math.isinf(v):
            raise ValueError(f"Embedding element {i} is {v}, expected finite float")
    return f"vecf32({vec})"


def _serialize_log_entry(entry: LogEntry) -> str:
    return json.dumps(entry.model_dump(mode="python"), default=_json_default)


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _deserialize_log_entry(s: str) -> LogEntry:
    data = json.loads(s)
    return LogEntry(**data)


def _make_log_entry(
    provenance: ProvenanceInput | None,
    note: str,
    event_time: datetime | None = None,
    happened_at: datetime | None = None,
) -> LogEntry:
    if provenance is None:
        raise ValueError("Log entry requires provenance")
    timestamp = event_time or datetime.now(tz=timezone.utc)
    return LogEntry(
        source_id=provenance.source_id,
        timestamp=timestamp,  # transaction time — when recorded/discussed
        happened_at=happened_at or timestamp,  # valid time — defaults to episode time
        note=note,
    )


def _node_from_props(
    props: dict[str, Any], log_tail: int | None = None
) -> SemanticNode:
    """Construct a SemanticNode from raw FalkorDB properties."""
    raw_log = props.get("log") or []
    raw_tail = raw_log[-log_tail:] if log_tail is not None else raw_log
    log = [_deserialize_log_entry(s) for s in raw_tail]
    return SemanticNode(
        id=props["id"],
        aliases=props.get("aliases") or [],
        summary=props["summary"],
        total_log_count=props.get("total_log_count", 0),
        log=log,
    )


def _build_outgoing_edges(
    node_id: str,
    raw_edges: list[list[Any] | None],
    log_tail: int | None = None,
) -> list[SemanticEdge]:
    edges: list[SemanticEdge] = []
    for edge_data in raw_edges:
        if edge_data is None:
            continue
        edge_id, label, to_id, fact, raw_log, total_log_count, source_id = edge_data
        if edge_id is None or to_id is None:
            continue
        full_log = raw_log or []
        tail = full_log[-log_tail:] if log_tail is not None else full_log
        edges.append(
            SemanticEdge(
                id=edge_id,
                from_node_id=node_id,
                to_node_id=to_id,
                label=label,
                fact=fact or "",
                total_log_count=total_log_count or 0,
                log=[_deserialize_log_entry(s) for s in tail],
                source_id=source_id,
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
    embedding: list[float] | None = None,
    event_time: datetime | None = None,
    happened_at: datetime | None = None,
) -> OperationResult:
    entry = _make_log_entry(provenance, note, event_time, happened_at)
    entry_json = _serialize_log_entry(entry)
    embedding_clause = ""
    if embedding is not None:
        embedding_clause = f", embedding: {_vecf32_literal(embedding)}"
    # `name` is not read by app code; it's the FalkorDB Browser display
    # caption (see store/system.py:init_system).
    graph.query(
        f"""
        CREATE (n:SemanticNode {{
            id: $id,
            name: $name,
            aliases: $aliases,
            summary: $summary,
            total_log_count: 1,
            log: [$entry_json]{embedding_clause}
        }})
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
    embedding: list[float] | None = None,
    current_summary: str | None = None,
    event_time: datetime | None = None,
    happened_at: datetime | None = None,
) -> OperationResult:
    effective_note = note
    if new_summary is not None:
        if current_summary is None:
            result = graph.query(
                "MATCH (n:SemanticNode {id: $id}) RETURN n.summary",
                {"id": node_id},
            )
            if not result.result_set:
                raise ValueError(f"SemanticNode '{node_id}' not found.")
            current_summary = result.result_set[0][0]
        effective_note = f"[archived summary] {current_summary} | Agent note: {note}"

    entry = _make_log_entry(provenance, effective_note, event_time, happened_at)
    entry_json = _serialize_log_entry(entry)

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
    if embedding is not None:
        set_parts.append(f"n.embedding = {_vecf32_literal(embedding)}")

    result = graph.query(
        f"MATCH (n:SemanticNode {{id: $id}}) SET {', '.join(set_parts)} RETURN n",
        params,
    )
    if not result.result_set:
        raise ValueError(f"SemanticNode '{node_id}' not found.")

    return OperationResult(ok=True, id=node_id)


def link_mention(graph: Graph, session_id: str, node_id: str) -> None:
    """Record that an episode touched a node: (:Session)-[:MENTIONS]->(:SemanticNode).

    Idempotent via MERGE — repeated touches in the same session do not duplicate.
    """
    graph.query(
        """
        MATCH (s:Session {id: $sid}), (n:SemanticNode {id: $nid})
        MERGE (s)-[:MENTIONS]->(n)
        """,
        {"sid": session_id, "nid": node_id},
    )


def delete_node(graph: Graph, node_id: str) -> OperationResult:
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
    fact: str,
    note: str,
    edge_id: str,
    provenance: ProvenanceInput | None,
    embedding: list[float] | None = None,
    event_time: datetime | None = None,
    happened_at: datetime | None = None,
    source_id: str | None = None,
) -> OperationResult:
    entry = _make_log_entry(provenance, note, event_time, happened_at)
    entry_json = _serialize_log_entry(entry)
    embedding_clause = (
        f", embedding: {_vecf32_literal(embedding)}" if embedding is not None else ""
    )
    result = graph.query(
        f"""
        MATCH (a:SemanticNode {{id: $from_id}}), (b:SemanticNode {{id: $to_id}})
        CREATE (a)-[r:RELATES {{
            id: $edge_id,
            label: $label,
            fact: $fact,
            total_log_count: 1,
            log: [$entry_json],
            source_id: $source_id{embedding_clause}
        }}]->(b)
        RETURN r
        """,
        {
            "from_id": from_node_id,
            "to_id": to_node_id,
            "edge_id": edge_id,
            "label": label,
            "fact": fact,
            "entry_json": entry_json,
            "source_id": source_id,
        },
    )
    if not result.result_set:
        # Domain refusal, not a system fault: report it as a result the agent
        # can react to (look up real ids and retry) instead of raising.
        return OperationResult(
            ok=False,
            message=(
                f"Not created — one or both nodes do not exist "
                f"(from='{from_node_id}', to='{to_node_id}'). Use node ids "
                f"returned by create_node/search_graph, then retry."
            ),
        )
    return OperationResult(ok=True, id=edge_id)


def update_edge(
    graph: Graph,
    edge_id: str,
    note: str,
    new_label: str | None = None,
    new_fact: str | None = None,
    provenance: ProvenanceInput | None = None,
    embedding: list[float] | None = None,
    event_time: datetime | None = None,
    happened_at: datetime | None = None,
) -> OperationResult:
    entry = _make_log_entry(provenance, note, event_time, happened_at)
    entry_json = _serialize_log_entry(entry)

    set_parts = [
        "r.log = r.log + [$entry_json]",
        "r.total_log_count = r.total_log_count + 1",
    ]
    params: dict[str, Any] = {"id": edge_id, "entry_json": entry_json}

    if new_label is not None:
        set_parts.append("r.label = $new_label")
        params["new_label"] = new_label
    if new_fact is not None:
        set_parts.append("r.fact = $new_fact")
        params["new_fact"] = new_fact
    if embedding is not None:
        set_parts.append(f"r.embedding = {_vecf32_literal(embedding)}")

    result = graph.query(
        f"MATCH ()-[r:RELATES {{id: $id}}]->() SET {', '.join(set_parts)} RETURN r",
        params,
    )
    if not result.result_set:
        raise ValueError(f"Edge '{edge_id}' not found.")
    return OperationResult(ok=True, id=edge_id)


def get_edge(graph: Graph, edge_id: str) -> SemanticEdge:
    result = graph.query(
        """
        MATCH (a:SemanticNode)-[r:RELATES {id: $id}]->(b:SemanticNode)
        RETURN r.id, r.label, r.fact, r.log, r.total_log_count, r.source_id, a.id, b.id
        """,
        {"id": edge_id},
    )
    if not result.result_set:
        raise ValueError(f"Edge '{edge_id}' not found.")
    eid, label, fact, raw_log, total_log_count, source_id, from_id, to_id = (
        result.result_set[0]
    )
    return SemanticEdge(
        id=eid,
        from_node_id=from_id,
        to_node_id=to_id,
        label=label,
        fact=fact or "",
        total_log_count=total_log_count or 0,
        log=[_deserialize_log_entry(s) for s in (raw_log or [])],
        source_id=source_id,
    )


def delete_edge(graph: Graph, edge_id: str) -> OperationResult:
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


def _node_row(
    node_id, aliases, summary, edge_count, distance: float | None = None
) -> SearchResult:
    return SearchResult(
        kind="node",
        id=node_id,
        label=aliases[0] if aliases else node_id,
        text=summary.splitlines()[0] if summary else "",
        distance=distance,
        edge_count=int(edge_count),
    )


def _edge_row(
    edge_id, label, fact, from_id, to_id, distance: float | None = None
) -> SearchResult:
    return SearchResult(
        kind="edge",
        id=edge_id,
        label=label or "",
        text=(fact or "").splitlines()[0] if fact else "",
        distance=distance,
        endpoints=[from_id, to_id],
    )


def _log_in_range(raw_log, start: datetime, end: datetime) -> bool:
    for entry_str in raw_log or []:
        entry = _deserialize_log_entry(entry_str)
        # Filter on valid time (when the fact was true); fall back to record time
        # for entries written before happened_at existed.
        when = entry.happened_at or entry.timestamp
        if start <= when <= end:
            return True
    return False


def _filter_by_time_range(
    graph: Graph,
    results: list[SearchResult],
    time_range: list[datetime],
) -> list[SearchResult]:
    """Keep only nodes/edges with at least one log entry within [start, end]."""
    if not results:
        return results
    start, end = time_range[0], time_range[1]
    node_ids = [r.id for r in results if r.kind == "node"]
    edge_ids = [r.id for r in results if r.kind == "edge"]
    passing: set[str] = set()

    if node_ids:
        rows = graph.query(
            "MATCH (n:SemanticNode) WHERE n.id IN $ids RETURN n.id, n.log",
            {"ids": node_ids},
        )
        for node_id, raw_log in rows.result_set:
            if _log_in_range(raw_log, start, end):
                passing.add(node_id)

    if edge_ids:
        rows = graph.query(
            "MATCH ()-[r:RELATES]->() WHERE r.id IN $ids RETURN r.id, r.log",
            {"ids": edge_ids},
        )
        for edge_id, raw_log in rows.result_set:
            if _log_in_range(raw_log, start, end):
                passing.add(edge_id)

    return [r for r in results if r.id in passing]


# Reciprocal Rank Fusion constant (standard choice; see Cormack et al. 2009).
# RRF combines the vector-distance ranking and the keyword match-tier ranking
# by rank position rather than raw magnitude, so a top keyword hit (e.g. an
# exact alias/title match) can outrank a middling vector hit instead of being
# structurally capped below every embedding result.
_RRF_K = 60


def _rrf_scores(ranked_ids: list[str]) -> dict[str, float]:
    return {rid: 1.0 / (_RRF_K + rank) for rank, rid in enumerate(ranked_ids, start=1)}


def search_graph(
    graph: Graph,
    *,
    query: str,
    limit: int = 10,
    query_embedding: list[float] | None = None,
    time_range: list[datetime] | None = None,
) -> SearchGraphOutput:
    rows: dict[str, SearchResult] = {}
    vector_hits: list[tuple[float, str]] = []

    if query_embedding is not None:
        vec_literal = _vecf32_literal(query_embedding)
        node_vec = graph.query(
            f"""
            CALL db.idx.vector.queryNodes(
                'SemanticNode', 'embedding', $limit, {vec_literal}
            ) YIELD node, score
            OPTIONAL MATCH (node)-[r:RELATES]-()
            WITH node, score, count(r) AS edge_count
            RETURN node.id, node.aliases, node.summary, edge_count, score
            """,
            {"limit": limit},
        )
        for nid, aliases, summary, edge_count, distance in node_vec.result_set:
            rows[nid] = _node_row(nid, aliases, summary, edge_count, float(distance))
            vector_hits.append((float(distance), nid))

        # FalkorDB indexes relationships separately; surface edge-facts in the same ranking.
        # Read endpoints via startNode()/endNode() rather than re-MATCHing `relationship` —
        # FalkorDB doesn't treat a YIELDed relationship as bound in a later MATCH pattern,
        # which silently collapses every row's `score` to the first row's value.
        edge_vec = graph.query(
            f"""
            CALL db.idx.vector.queryRelationships(
                'RELATES', 'embedding', $limit, {vec_literal}
            ) YIELD relationship, score
            RETURN relationship.id, relationship.label, relationship.fact,
                   startNode(relationship).id, endNode(relationship).id, score
            """,
            {"limit": limit},
        )
        for eid, label, fact, from_id, to_id, distance in edge_vec.result_set:
            rows[eid] = _edge_row(eid, label, fact, from_id, to_id, float(distance))
            vector_hits.append((float(distance), eid))

    # match_tier 0 = the query hit the entity's identity (alias/label), the
    # strongest keyword signal; 1 = it only hit free text (summary/fact).
    # Ordering by tier gives keyword hits a real rank to feed into RRF instead
    # of leaving them all tied with no way to compare to each other or to
    # vector hits.
    node_kw = graph.query(
        """
        MATCH (n:SemanticNode)
        WHERE ANY(a IN n.aliases WHERE toLower(a) CONTAINS toLower($query))
           OR toLower(n.summary) CONTAINS toLower($query)
        OPTIONAL MATCH (n)-[r:RELATES]-()
        WITH n, count(r) AS edge_count,
             CASE WHEN ANY(a IN n.aliases WHERE toLower(a) CONTAINS toLower($query))
                  THEN 0 ELSE 1 END AS match_tier
        RETURN n.id, n.aliases, n.summary, edge_count, match_tier
        ORDER BY match_tier ASC, edge_count DESC
        LIMIT $limit
        """,
        {"query": query, "limit": limit},
    )
    keyword_hits: list[tuple[int, str]] = []
    for nid, aliases, summary, edge_count, match_tier in node_kw.result_set:
        if nid not in rows:
            rows[nid] = _node_row(nid, aliases, summary, edge_count)
        keyword_hits.append((match_tier, nid))

    edge_kw = graph.query(
        """
        MATCH (a:SemanticNode)-[r:RELATES]->(b:SemanticNode)
        WHERE toLower(r.label) CONTAINS toLower($query)
           OR toLower(r.fact) CONTAINS toLower($query)
        WITH a, b, r,
             CASE WHEN toLower(r.label) CONTAINS toLower($query)
                  THEN 0 ELSE 1 END AS match_tier
        RETURN r.id, r.label, r.fact, a.id, b.id, match_tier
        ORDER BY match_tier ASC
        LIMIT $limit
        """,
        {"query": query, "limit": limit},
    )
    for eid, label, fact, from_id, to_id, match_tier in edge_kw.result_set:
        if eid not in rows:
            rows[eid] = _edge_row(eid, label, fact, from_id, to_id)
        keyword_hits.append((match_tier, eid))

    vector_rank = [rid for _, rid in sorted(vector_hits, key=lambda t: t[0])]
    keyword_rank = [rid for _, rid in sorted(keyword_hits, key=lambda t: t[0])]
    vector_scores = _rrf_scores(vector_rank)
    keyword_scores = _rrf_scores(keyword_rank)
    fused = {
        rid: vector_scores.get(rid, 0.0) + keyword_scores.get(rid, 0.0) for rid in rows
    }

    results = sorted(rows.values(), key=lambda r: fused[r.id], reverse=True)[:limit]
    if time_range:
        results = _filter_by_time_range(graph, results, time_range)
    return SearchGraphOutput(results=results)


def find_similar_nodes(
    graph: Graph,
    *,
    aliases: list[str],
    embedding: list[float],
    max_distance: float,
    limit: int = 3,
) -> list[tuple[str, str, float]]:
    """Existing nodes that likely denote the same entity as a prospective write.

    A node matches if it shares an alias (case-insensitive) or its embedding is
    within *max_distance* (cosine). Returns [(node_id, canonical_alias,
    distance)] ordered nearest-first; alias matches without a close vector
    report distance as found by the vector query or ``max_distance`` if
    outside its top-k.

    Queries the single ``embedding`` index — every node's embedding is aliases
    + current summary only, so the candidate's own aliases+summary vector
    always compares apples-to-apples against it.
    """
    candidates: dict[str, tuple[str, float]] = {}

    rows = graph.query(
        f"""
        CALL db.idx.vector.queryNodes(
            'SemanticNode', 'embedding', $limit, {_vecf32_literal(embedding)}
        ) YIELD node, score
        RETURN node.id, node.aliases, score
        """,
        {"limit": limit},
    )
    lowered = {a.lower() for a in aliases}
    for nid, node_aliases, score in rows.result_set:
        alias_hit = any(a.lower() in lowered for a in node_aliases or [])
        if float(score) <= max_distance or alias_hit:
            canonical = (node_aliases or [nid])[0]
            candidates[nid] = (canonical, float(score))

    alias_rows = graph.query(
        """
        MATCH (n:SemanticNode)
        WHERE ANY(a IN n.aliases WHERE toLower(a) IN $aliases)
        RETURN n.id, n.aliases
        LIMIT $limit
        """,
        {"aliases": list(lowered), "limit": limit},
    )
    for nid, node_aliases in alias_rows.result_set:
        if nid not in candidates:
            candidates[nid] = ((node_aliases or [nid])[0], max_distance)

    return sorted(
        [(nid, alias, dist) for nid, (alias, dist) in candidates.items()],
        key=lambda t: t[2],
    )[:limit]


def get_node(graph: Graph, node_id: str) -> GetNodeResult:
    nodes_by_id = get_nodes(graph, [node_id])
    try:
        return nodes_by_id[node_id]
    except KeyError as exc:
        raise ValueError(f"SemanticNode '{node_id}' not found.") from exc


def get_nodes(graph: Graph, node_ids: list[str]) -> dict[str, GetNodeResult]:
    if not node_ids:
        return {}

    # Fetch node properties, outgoing edges, and source episodes in one query.
    result = graph.query(
        """
        MATCH (n:SemanticNode)
        WHERE n.id IN $ids
        OPTIONAL MATCH (n)-[r:RELATES]->(m:SemanticNode)
        WITH n, collect(CASE WHEN r IS NOT NULL THEN [r.id, r.label, m.id, r.fact, r.log, r.total_log_count, r.source_id] ELSE null END) AS edges
        OPTIONAL MATCH (s:Session)-[:MENTIONS]->(n)
        RETURN n.id, n, edges, collect(DISTINCT s.id) AS mentioned_by
        """,
        {"ids": node_ids},
    )

    nodes_by_id: dict[str, GetNodeResult] = {}
    for found_node_id, raw_node, raw_edges, mentioned_by in result.result_set:
        node_props = raw_node.properties
        nodes_by_id[found_node_id] = GetNodeResult(
            node=_node_from_props(node_props),
            edges=_build_outgoing_edges(found_node_id, raw_edges or [], log_tail=2),
            mentioned_by=[sid for sid in (mentioned_by or []) if sid is not None],
        )
    return nodes_by_id


def get_node_neighborhood(graph: Graph, node_id: str) -> GetNodeNeighborhoodOutput:
    result = graph.query(
        """
        MATCH (n:SemanticNode {id: $id})
        OPTIONAL MATCH (n)-[r:RELATES]-(m:SemanticNode)
        RETURN n, collect(CASE WHEN r IS NOT NULL THEN [r.id, r.label, m.id, m.aliases, m.summary, r.fact] ELSE null END) AS neighbor_data
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
        (
            edge_id,
            edge_label,
            neighbor_id,
            neighbor_aliases,
            neighbor_summary,
            edge_fact,
        ) = nd
        if edge_id is None or edge_id in seen_edge_ids:
            continue
        seen_edge_ids.add(edge_id)
        canonical = neighbor_aliases[0] if neighbor_aliases else neighbor_id
        summary_line = neighbor_summary.splitlines()[0] if neighbor_summary else ""
        neighbors.append(
            NeighborSummary(
                edge_id=edge_id,
                edge_label=edge_label,
                edge_fact=edge_fact,
                node_id=neighbor_id,
                canonical_alias=canonical,
                summary_line=summary_line,
            )
        )

    return GetNodeNeighborhoodOutput(node=node, neighbors=neighbors)
