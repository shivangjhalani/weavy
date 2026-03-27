"""FalkorDB graph module: init, atomic CRUD, and vector search.

All node/edge mutation operations atomically re-embed the summary.
No separate embedding update path is exposed — GRPH-05 enforced here.
"""

import json
from datetime import datetime, timezone

from falkordb import FalkorDB
from redis.exceptions import ResponseError

from lifeos.core.embeddings import embed_query, embed_text
from lifeos.memory.models import Edge, LogEntry, Node, TranscriptRef


def init_graph(
    host: str = "localhost",
    port: int = 6379,
    graph_name: str = "lifeos",
):
    """Connect to FalkorDB and initialize all indexes.

    Creates range indexes on Node.name, Node.aliases, Node.transcript_id,
    an edge index on EDGE.label, and a vector index on Node.embedding
    (3072d, cosine).

    Index creation is wrapped in try/except so calling init_graph twice
    (or when indexes already exist) does not raise.

    Returns the FalkorDB graph object.
    """
    db = FalkorDB(host=host, port=port)
    graph = db.select_graph(graph_name)

    # Range indexes for fast property lookups
    range_indexes = [
        "CREATE INDEX FOR (n:Node) ON (n.name)",
        "CREATE INDEX FOR (n:Node) ON (n.transcript_id)",
        "CREATE INDEX FOR (n:Node) ON (n.aliases)",
        "CREATE INDEX FOR ()-[r:EDGE]->() ON (r.label)",
    ]
    for ddl in range_indexes:
        try:
            graph.query(ddl)
        except ResponseError as e:
            if "already indexed" not in str(e).lower():
                raise

    # Vector index on embedding (3072 dims, cosine similarity)
    try:
        graph.query(
            "CREATE VECTOR INDEX FOR (n:Node) ON (n.embedding) "
            "OPTIONS {dimension:3072, similarityFunction:'cosine'}"
        )
    except ResponseError as e:
        if "already indexed" not in str(e).lower():
            raise

    # Vector index on EDGE embedding (3072 dims, cosine similarity)
    try:
        graph.query(
            "CREATE VECTOR INDEX FOR ()-[r:EDGE]->() ON (r.embedding) "
            "OPTIONS {dimension:3072, similarityFunction:'cosine'}"
        )
    except ResponseError as e:
        if "already indexed" not in str(e).lower():
            raise

    return graph


def create_node(graph, node: Node) -> None:
    """Store a node in the graph, embedding its summary atomically.

    Complex nested objects (log, refs) are stored as JSON strings since
    FalkorDB properties must be primitives or arrays of primitives.
    """
    embedding = embed_text(node.summary)
    ts = datetime.now(timezone.utc).isoformat()
    log_json = json.dumps([entry.model_dump(mode="json") for entry in node.log])
    refs_json = json.dumps([ref.model_dump(mode="json") for ref in node.refs])

    graph.query(
        """
        CREATE (n:Node {
            id: $id,
            name: $name,
            summary: $summary,
            aliases: $aliases,
            embedding: vecf32($embedding),
            log: $log_json,
            refs: $refs_json,
            created_at: $ts,
            updated_at: $ts
        })
        """,
        {
            "id": node.id,
            "name": node.name,
            "summary": node.summary,
            "aliases": node.aliases,
            "embedding": embedding,
            "log_json": log_json,
            "refs_json": refs_json,
            "ts": ts,
        },
    )


def update_node(
    graph,
    node_id: str,
    new_summary: str,
    log_entry: str,
    transcript_ref: dict | None = None,
    new_aliases: list[str] | None = None,
    new_refs: list[TranscriptRef] | None = None,
    new_name: str | None = None,
    recorded_at: datetime | None = None,
) -> None:
    """Update a node's summary and re-embed atomically (GRPH-05).

    Appends a new LogEntry to the node's log. Always re-embeds — no
    separate embedding update path exists.

    Optional params:
    - new_aliases: merged (union, no duplicates) with existing aliases
    - new_refs: appended to existing refs
    - new_name: replaces the node's name
    - recorded_at: timestamp for the LogEntry (defaults to now)
    """
    # Always re-embed per GRPH-05
    embedding = embed_text(new_summary)
    entry_ts = recorded_at if recorded_at is not None else datetime.now(timezone.utc)
    ts = datetime.now(timezone.utc).isoformat()

    # Read existing node for log, refs, aliases
    existing = get_node(graph, node_id)

    # Merge log
    existing_log: list = json.loads(existing["log"]) if existing and existing.get("log") else []
    new_entry = LogEntry(recorded_at=entry_ts, note=log_entry)
    existing_log.append(new_entry.model_dump(mode="json"))
    log_json = json.dumps(existing_log)

    # Merge refs if provided
    refs_json: str | None = None
    if new_refs is not None:
        existing_refs: list = json.loads(existing["refs"]) if existing and existing.get("refs") else []
        existing_refs.extend([r.model_dump(mode="json") for r in new_refs])
        refs_json = json.dumps(existing_refs)

    # Merge aliases if provided (union, no duplicates)
    merged_aliases: list[str] | None = None
    if new_aliases is not None:
        existing_aliases: list[str] = []
        if existing and existing.get("aliases"):
            existing_aliases = list(existing["aliases"])
        # Union preserving order
        seen = set(existing_aliases)
        for a in new_aliases:
            if a not in seen:
                existing_aliases.append(a)
                seen.add(a)
        merged_aliases = existing_aliases

    # Build dynamic SET clause
    set_parts = [
        "n.summary = $summary",
        "n.embedding = vecf32($embedding)",
        "n.log = $log_json",
        "n.updated_at = $ts",
    ]
    params: dict = {
        "id": node_id,
        "summary": new_summary,
        "embedding": embedding,
        "log_json": log_json,
        "ts": ts,
    }

    if refs_json is not None:
        set_parts.append("n.refs = $refs_json")
        params["refs_json"] = refs_json

    if merged_aliases is not None:
        set_parts.append("n.aliases = $aliases")
        params["aliases"] = merged_aliases

    if new_name is not None:
        set_parts.append("n.name = $new_name")
        params["new_name"] = new_name

    # FalkorDB requires REMOVE before SET for vecf32 vector properties —
    # direct overwrite with SET does not update the stored vector value.
    graph.query(
        "MATCH (n:Node {id: $id}) REMOVE n.embedding",
        {"id": node_id},
    )
    set_clause = ", ".join(set_parts)
    graph.query(
        f"MATCH (n:Node {{id: $id}}) SET {set_clause}",
        params,
    )


def create_edge(graph, edge: Edge) -> None:
    """Store an edge between two nodes, embedding its summary atomically."""
    embedding = embed_text(edge.summary)
    ts = datetime.now(timezone.utc).isoformat()
    log_json = json.dumps([entry.model_dump(mode="json") for entry in edge.log])
    refs_json = json.dumps([ref.model_dump(mode="json") for ref in edge.refs])

    graph.query(
        """
        MATCH (s:Node {id: $source_id}), (t:Node {id: $target_id})
        CREATE (s)-[r:EDGE {
            id: $id,
            label: $label,
            summary: $summary,
            embedding: vecf32($embedding),
            log: $log_json,
            refs: $refs_json,
            created_at: $ts,
            updated_at: $ts
        }]->(t)
        """,
        {
            "id": edge.id,
            "label": edge.label,
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "summary": edge.summary,
            "embedding": embedding,
            "log_json": log_json,
            "refs_json": refs_json,
            "ts": ts,
        },
    )


def update_edge(
    graph,
    edge_id: str,
    new_summary: str,
    log_entry: str,
    new_refs: list[TranscriptRef] | None = None,
    recorded_at: datetime | None = None,
) -> None:
    """Update an edge's summary and re-embed atomically (GRPH-05).

    Appends a new LogEntry to the edge's log. Always re-embeds.

    Optional params:
    - new_refs: appended to existing refs
    - recorded_at: timestamp for the LogEntry (defaults to now)
    """
    embedding = embed_text(new_summary)
    entry_ts = recorded_at if recorded_at is not None else datetime.now(timezone.utc)
    ts = datetime.now(timezone.utc).isoformat()

    # Read existing log
    existing = graph.query(
        "MATCH ()-[r:EDGE {id: $id}]->() RETURN r.log, r.refs",
        {"id": edge_id},
    )
    existing_log: list = []
    existing_refs_raw: str | None = None
    if existing.result_set:
        row = existing.result_set[0]
        existing_log = json.loads(row[0]) if row[0] else []
        existing_refs_raw = row[1] if len(row) > 1 else None

    new_entry = LogEntry(recorded_at=entry_ts, note=log_entry)
    existing_log.append(new_entry.model_dump(mode="json"))
    log_json = json.dumps(existing_log)

    # Merge refs if provided
    refs_json: str | None = None
    if new_refs is not None:
        existing_refs: list = json.loads(existing_refs_raw) if existing_refs_raw else []
        existing_refs.extend([r.model_dump(mode="json") for r in new_refs])
        refs_json = json.dumps(existing_refs)

    # Build dynamic SET clause
    set_parts = [
        "r.summary = $summary",
        "r.embedding = vecf32($embedding)",
        "r.log = $log_json",
        "r.updated_at = $ts",
    ]
    params: dict = {
        "id": edge_id,
        "summary": new_summary,
        "embedding": embedding,
        "log_json": log_json,
        "ts": ts,
    }

    if refs_json is not None:
        set_parts.append("r.refs = $refs_json")
        params["refs_json"] = refs_json

    # FalkorDB requires REMOVE before SET for vecf32 vector properties.
    graph.query(
        "MATCH ()-[r:EDGE {id: $id}]->() REMOVE r.embedding",
        {"id": edge_id},
    )
    set_clause = ", ".join(set_parts)
    graph.query(
        f"MATCH ()-[r:EDGE {{id: $id}}]->() SET {set_clause}",
        params,
    )


def delete_node(graph, node_id: str) -> None:
    """Delete a node and all its relationships from the graph."""
    graph.query("MATCH (n:Node {id: $id}) DETACH DELETE n", {"id": node_id})


def delete_edge(graph, edge_id: str) -> None:
    """Delete an edge from the graph by its id."""
    graph.query("MATCH ()-[r:EDGE {id: $id}]->() DELETE r", {"id": edge_id})


def search_nodes_by_alias(graph, alias: str) -> list[dict]:
    """Find nodes whose aliases list contains the given alias (exact match).

    Returns a list of dicts with id, name, aliases, summary fields.
    """
    result = graph.query(
        "MATCH (n:Node) WHERE $alias IN n.aliases "
        "RETURN n.id, n.name, n.aliases, n.summary",
        {"alias": alias},
    )
    return [
        {"id": row[0], "name": row[1], "aliases": row[2], "summary": row[3]}
        for row in result.result_set
    ]


def set_node_log(graph, node_id: str, log_entries: list[dict]) -> None:
    """Replace a node's log with the given entries (for compression pass).

    Does NOT re-embed — summary and embedding remain unchanged.
    """
    log_json = json.dumps(log_entries, default=str)
    graph.query(
        "MATCH (n:Node {id: $id}) SET n.log = $log_json, n.updated_at = $ts",
        {"id": node_id, "log_json": log_json, "ts": datetime.now(timezone.utc).isoformat()},
    )


def set_edge_log(graph, edge_id: str, log_entries: list[dict]) -> None:
    """Replace an edge's log with the given entries (for compression pass).

    Does NOT re-embed — summary and embedding remain unchanged.
    """
    log_json = json.dumps(log_entries, default=str)
    graph.query(
        "MATCH ()-[r:EDGE {id: $id}]->() SET r.log = $log_json, r.updated_at = $ts",
        {"id": edge_id, "log_json": log_json, "ts": datetime.now(timezone.utc).isoformat()},
    )


def vector_search(
    graph, query_text: str, k: int = 5
) -> list[tuple[str, str, list, str, float]]:
    """Semantic KNN search over node summaries.

    Uses embed_query() (RETRIEVAL_QUERY task type) for the query embedding,
    then calls FalkorDB's native vector index procedure.

    Returns a list of (node_id, name, aliases, summary, score) tuples ordered by score DESC.
    """
    query_embedding = embed_query(query_text)

    result = graph.query(
        "CALL db.idx.vector.queryNodes('Node', 'embedding', $k, vecf32($embedding)) "
        "YIELD node, score "
        "RETURN node.id, node.name, node.aliases, node.summary, score "
        "ORDER BY score DESC",
        {"k": k, "embedding": query_embedding},
    )

    return [
        (row[0], row[1], row[2], row[3], float(row[4]))
        for row in result.result_set
    ]


def vector_search_edges(
    graph, query_text: str, k: int = 5
) -> list[tuple[str, str, float]]:
    """Semantic KNN search over edge summaries.

    Attempts to use FalkorDB's native EDGE vector index via
    db.idx.vector.queryRelationships. Falls back to a full-scan
    cosine comparison if the procedure is unavailable.

    Returns a list of (edge_id, summary, score) tuples ordered by score DESC.
    """
    query_embedding = embed_query(query_text)

    try:
        result = graph.query(
            "CALL db.idx.vector.queryRelationships('EDGE', 'embedding', $k, vecf32($embedding)) "
            "YIELD relationship, score "
            "RETURN relationship.id, relationship.summary, score "
            "ORDER BY score DESC",
            {"k": k, "embedding": query_embedding},
        )
        return [
            (row[0], row[1], float(row[2]))
            for row in result.result_set
        ]
    except (ResponseError, Exception):
        # Fallback: full-scan cosine comparison
        all_edges = graph.query(
            "MATCH ()-[r:EDGE]->() RETURN r.id, r.summary, r.embedding",
        )
        if not all_edges.result_set:
            return []

        import math

        def cosine_sim(a: list, b: list) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            mag_a = math.sqrt(sum(x * x for x in a))
            mag_b = math.sqrt(sum(y * y for y in b))
            if mag_a == 0 or mag_b == 0:
                return 0.0
            return dot / (mag_a * mag_b)

        scored = []
        for row in all_edges.result_set:
            edge_id, summary, embedding = row[0], row[1], row[2]
            if embedding is not None:
                score = cosine_sim(list(query_embedding), list(embedding))
                scored.append((edge_id, summary, float(score)))

        scored.sort(key=lambda x: x[2], reverse=True)
        return scored[:k]


def get_node(graph, node_id: str) -> dict | None:
    """Retrieve a node's properties by id, or None if not found."""
    result = graph.query(
        "MATCH (n:Node {id: $id}) RETURN n",
        {"id": node_id},
    )
    if not result.result_set:
        return None

    node = result.result_set[0][0]
    return dict(node.properties)


def get_node_edges(graph, node_id: str) -> list[dict]:
    """Retrieve all edges connected to a node (both outgoing and incoming).

    Direction is from the perspective of node_id:
    - 'outgoing': node_id is the source
    - 'incoming': node_id is the target

    Returns list of dicts, each with:
        edge_id, label, summary, source (dict with id+name),
        target (dict with id+name), direction
    Does NOT include per-edge refs or log (use get_edge for those).
    """
    result = graph.query(
        """
        MATCH (n:Node {id: $id})-[r:EDGE]->(m:Node)
        RETURN r.id, r.label, r.summary, n.id, n.name, m.id, m.name, 'outgoing'
        UNION
        MATCH (n:Node {id: $id})<-[r:EDGE]-(m:Node)
        RETURN r.id, r.label, r.summary, m.id, m.name, n.id, n.name, 'incoming'
        """,
        {"id": node_id},
    )
    edges = []
    for row in result.result_set:
        edges.append({
            "edge_id": row[0],
            "label": row[1],
            "summary": row[2],
            "source": {"id": row[3], "name": row[4]},
            "target": {"id": row[5], "name": row[6]},
            "direction": row[7],
        })
    return edges


def get_edge(graph, edge_id: str) -> dict | None:
    """Retrieve a full edge by id, or None if not found.

    Returns dict with:
        edge_id, label, summary, source_id, target_id,
        log (parsed list of {recorded_at, note} dicts),
        refs (parsed list of {transcript_id, start_offset, end_offset} dicts),
        created_at, updated_at

    Embedding is excluded — internal FalkorDB artifact with no meaning to the LLM.
    """
    result = graph.query(
        """
        MATCH (s:Node)-[r:EDGE {id: $id}]->(t:Node)
        RETURN r.id, r.label, r.summary, s.id, t.id,
               r.log, r.refs, r.created_at, r.updated_at
        """,
        {"id": edge_id},
    )
    if not result.result_set:
        return None
    row = result.result_set[0]
    log_entries = json.loads(row[5]) if row[5] else []
    refs_list = json.loads(row[6]) if row[6] else []
    return {
        "edge_id": row[0],
        "label": row[1],
        "summary": row[2],
        "source_id": row[3],
        "target_id": row[4],
        "log": log_entries,
        "refs": refs_list,
        "created_at": row[7],
        "updated_at": row[8],
    }
