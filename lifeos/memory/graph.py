"""FalkorDB graph module: init, atomic CRUD, and vector search.

All node/edge mutation operations atomically re-embed the summary.
No separate embedding update path is exposed — GRPH-05 enforced here.
"""

import json
from datetime import datetime, timezone

from falkordb import FalkorDB

from lifeos.core.embeddings import embed_query, embed_text
from lifeos.memory.models import Edge, LogEntry, Node


def init_graph(
    host: str = "localhost",
    port: int = 6379,
    graph_name: str = "lifeos",
):
    """Connect to FalkorDB and initialize all indexes.

    Creates range indexes on Node.name, Node.type, Node.transcript_id,
    Node.aliases, and a vector index on Node.embedding (3072d, cosine).

    Index creation is wrapped in try/except so calling init_graph twice
    (or when indexes already exist) does not raise.

    Returns the FalkorDB graph object.
    """
    db = FalkorDB(host=host, port=port)
    graph = db.select_graph(graph_name)

    # Range indexes for fast property lookups
    range_indexes = [
        "CREATE INDEX FOR (n:Node) ON (n.name)",
        "CREATE INDEX FOR (n:Node) ON (n.type)",
        "CREATE INDEX FOR (n:Node) ON (n.transcript_id)",
        "CREATE INDEX FOR (n:Node) ON (n.aliases)",
    ]
    for ddl in range_indexes:
        try:
            graph.query(ddl)
        except Exception:
            # "Index already exists" — safe to ignore
            pass

    # Vector index on embedding (3072 dims, cosine similarity)
    try:
        graph.query(
            "CREATE VECTOR INDEX FOR (n:Node) ON (n.embedding) "
            "OPTIONS {dimension:3072, similarityFunction:'cosine'}"
        )
    except Exception:
        # Already exists — safe to ignore
        pass

    return graph


def create_node(graph, node: Node) -> None:
    """Store a node in the graph, embedding its summary atomically.

    Complex nested objects (log, refs) are stored as JSON strings since
    FalkorDB properties must be primitives or arrays of primitives.
    """
    embedding = embed_text(node.summary)
    ts = datetime.now(timezone.utc).isoformat()
    name = node.aliases[0] if node.aliases else node.id
    log_json = json.dumps([entry.model_dump(mode="json") for entry in node.log])
    refs_json = json.dumps([ref.model_dump(mode="json") for ref in node.refs])

    graph.query(
        """
        CREATE (n:Node {
            id: $id,
            name: $name,
            type: $type,
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
            "name": name,
            "type": node.type,
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
) -> None:
    """Update a node's summary and re-embed atomically (GRPH-05).

    Appends a new LogEntry to the node's log. Always re-embeds — no
    separate embedding update path exists.
    """
    # Always re-embed per GRPH-05
    embedding = embed_text(new_summary)
    ts = datetime.now(timezone.utc).isoformat()

    # Read existing log, append new entry, serialize back
    existing = get_node(graph, node_id)
    existing_log: list = []
    if existing and existing.get("log"):
        try:
            existing_log = json.loads(existing["log"])
        except (json.JSONDecodeError, TypeError):
            existing_log = []

    new_entry = LogEntry(
        recorded_at=datetime.now(timezone.utc),
        note=log_entry,
    )
    existing_log.append(new_entry.model_dump(mode="json"))
    log_json = json.dumps(existing_log)

    # FalkorDB requires REMOVE before SET for vecf32 vector properties —
    # direct overwrite with SET does not update the stored vector value.
    graph.query(
        "MATCH (n:Node {id: $id}) REMOVE n.embedding",
        {"id": node_id},
    )
    graph.query(
        """
        MATCH (n:Node {id: $id})
        SET n.summary = $summary,
            n.embedding = vecf32($embedding),
            n.log = $log_json,
            n.updated_at = $ts
        """,
        {
            "id": node_id,
            "summary": new_summary,
            "embedding": embedding,
            "log_json": log_json,
            "ts": ts,
        },
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
            type: $type,
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
            "type": edge.type,
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
) -> None:
    """Update an edge's summary and re-embed atomically (GRPH-05).

    Appends a new LogEntry to the edge's log. Always re-embeds.
    """
    embedding = embed_text(new_summary)
    ts = datetime.now(timezone.utc).isoformat()

    # Read existing log
    existing = graph.query(
        "MATCH ()-[r:EDGE {id: $id}]->() RETURN r.log",
        {"id": edge_id},
    )
    existing_log: list = []
    if existing.result_set and existing.result_set[0][0]:
        try:
            existing_log = json.loads(existing.result_set[0][0])
        except (json.JSONDecodeError, TypeError):
            existing_log = []

    new_entry = LogEntry(
        recorded_at=datetime.now(timezone.utc),
        note=log_entry,
    )
    existing_log.append(new_entry.model_dump(mode="json"))
    log_json = json.dumps(existing_log)

    # FalkorDB requires REMOVE before SET for vecf32 vector properties.
    graph.query(
        "MATCH ()-[r:EDGE {id: $id}]->() REMOVE r.embedding",
        {"id": edge_id},
    )
    graph.query(
        """
        MATCH ()-[r:EDGE {id: $id}]->()
        SET r.summary = $summary,
            r.embedding = vecf32($embedding),
            r.log = $log_json,
            r.updated_at = $ts
        """,
        {
            "id": edge_id,
            "summary": new_summary,
            "embedding": embedding,
            "log_json": log_json,
            "ts": ts,
        },
    )


def vector_search(
    graph, query_text: str, k: int = 5
) -> list[tuple[str, str, float]]:
    """Semantic KNN search over node summaries.

    Uses embed_query() (RETRIEVAL_QUERY task type) for the query embedding,
    then calls FalkorDB's native vector index procedure.

    Returns a list of (node_id, summary, score) tuples ordered by score DESC.
    """
    query_embedding = embed_query(query_text)

    result = graph.query(
        "CALL db.idx.vector.queryNodes('Node', 'embedding', $k, vecf32($embedding)) "
        "YIELD node, score "
        "RETURN node.id, node.summary, score "
        "ORDER BY score DESC",
        {"k": k, "embedding": query_embedding},
    )

    return [
        (row[0], row[1], float(row[2]))
        for row in result.result_set
    ]


def get_node(graph, node_id: str) -> dict | None:
    """Retrieve a node's properties by id, or None if not found."""
    result = graph.query(
        "MATCH (n:Node {id: $id}) RETURN n",
        {"id": node_id},
    )
    if not result.result_set:
        return None

    node = result.result_set[0][0]
    # FalkorDB returns a Node object; extract its properties
    props = {}
    if hasattr(node, "properties"):
        props = dict(node.properties)
    elif isinstance(node, dict):
        props = node
    return props
