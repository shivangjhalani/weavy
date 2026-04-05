"""
Semantic graph CRUD — SemanticNode and SemanticEdge operations in FalkorDB.
Implemented in Phase 3.
"""

import json
from datetime import datetime, timezone

import litellm
import tiktoken
from falkordb import Graph

from weavy.config import settings
from weavy.models.graph import FenceEntry, LogEntry, ProvenanceInput, SemanticEdge, SemanticNode
from weavy.models.tools import (
    GetColdLogsOutput,
    GetNodeNeighborhoodOutput,
    GetNodeResult,
    NeighborSummary,
    OperationResult,
    SearchGraphInput,
    SearchGraphOutput,
    SearchResult,
)

_ENC = tiktoken.get_encoding("cl100k_base")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_log_entry(entry: LogEntry | FenceEntry) -> str:
    return json.dumps(entry.model_dump(mode="python"), default=_json_default)


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _deserialize_log_entry(s: str) -> LogEntry | FenceEntry:
    data = json.loads(s)
    if data.get("is_fence"):
        return FenceEntry(**data)
    return LogEntry(**data)


def _split_log(
    entries: list[LogEntry | FenceEntry],
) -> tuple[list[LogEntry | FenceEntry], FenceEntry | None, list[LogEntry | FenceEntry]]:
    """Split log into (cold, last_fence, hot).

    hot  = everything after the last FenceEntry (all entries if no fence)
    cold = everything strictly before the last FenceEntry
    """
    last_fence_idx = -1
    for i, entry in enumerate(entries):
        if isinstance(entry, FenceEntry):
            last_fence_idx = i

    if last_fence_idx == -1:
        return [], None, entries

    cold = entries[:last_fence_idx]
    last_fence = entries[last_fence_idx]
    hot = entries[last_fence_idx + 1 :]
    assert isinstance(last_fence, FenceEntry)
    return cold, last_fence, hot


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
    try:
        embedding = generate_embedding(aliases, summary)
        graph.query(
            "MATCH (n:SemanticNode {id: $id}) SET n.embedding = vecf32($embedding)",
            {"id": node_id, "embedding": embedding},
        )
    except Exception:
        pass
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
        try:
            effective_aliases = new_aliases if new_aliases is not None else props.get("aliases", [])
            effective_summary = new_summary if new_summary is not None else current_summary
            embedding = generate_embedding(effective_aliases, effective_summary)
            graph.query(
                "MATCH (n:SemanticNode {id: $id}) SET n.embedding = vecf32($embedding)",
                {"id": node_id, "embedding": embedding},
            )
        except Exception:
            pass

    return OperationResult(ok=True, id=node_id)


def delete_node(graph: Graph, node_id: str, reason: str) -> OperationResult:  # noqa: ARG001
    result = graph.query(
        "MATCH (n:SemanticNode {id: $id}) DETACH DELETE n RETURN count(n)",
        {"id": node_id},
    )
    # FalkorDB returns the count of deleted nodes; 0 means node was not found
    # We still return ok=True as a silent no-op is fine for idempotent deletes,
    # but raise if the node simply never existed to avoid masking bugs.
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
    try:
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
    except Exception:
        pass  # No index or embeddings yet — degrade to keyword-only

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
    cold, last_fence, hot = _split_log(all_entries)

    # Construct SemanticNode with only [last_fence] + hot in .log
    trimmed_log: list[LogEntry | FenceEntry] = []
    if last_fence is not None:
        trimmed_log.append(last_fence)
    trimmed_log.extend(hot)

    node = SemanticNode(
        id=node_props["id"],
        aliases=node_props.get("aliases") or [],
        summary=node_props["summary"],
        embedding=None,
        total_log_count=node_props.get("total_log_count", 0),
        log=trimmed_log,
    )

    # Build edge list (skip null placeholders from COLLECT when no edges exist)
    edges = []
    for edge_data in raw_edges:
        if edge_data is None:
            continue
        edge_id, label, to_id = edge_data
        if edge_id is not None:
            edges.append(SemanticEdge(id=edge_id, from_node_id=node_id, to_node_id=to_id, label=label))

    # Build cold hint
    cold_hint: str | None = None
    if cold:
        fence_count = sum(1 for e in cold if isinstance(e, FenceEntry))
        regular_count = sum(1 for e in cold if isinstance(e, LogEntry))
        timestamps = [e.timestamp for e in cold]
        earliest = min(timestamps)
        latest = max(timestamps)
        date_range = f" ({earliest.strftime('%b %Y')} \u2192 {latest.strftime('%b %Y')})"
        cold_hint = (
            f"{fence_count} fence(s) behind covering {regular_count} entries{date_range}. "
            f"Use get_cold_logs({node_id}) to retrieve."
        )

    return GetNodeResult(node=node, edges=edges, cold_hint=cold_hint)


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
    _, _, hot = _split_log(all_entries)

    # Return last 2 hot entries for orientation
    orientation_log: list[LogEntry | FenceEntry] = hot[-2:] if hot else []

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


# ---------------------------------------------------------------------------
# Fence creation
# ---------------------------------------------------------------------------


def _hot_segment_token_count(hot_entries: list) -> int:
    """Estimate token count of hot log entries using tiktoken."""
    return sum(len(_ENC.encode(_serialize_log_entry(e))) for e in hot_entries)


def create_fence(
    graph: Graph, node_id: str, model: str, node_output: "GetNodeResult | None" = None
) -> None:
    """
    Summarize the hot log segment of a node into a FenceEntry and append it.
    No-op if the hot segment is empty.
    """
    if node_output is None:
        node_output = get_node(graph, node_id)
    _, _, hot = _split_log(node_output.node.log)
    regular_hot = [e for e in hot if isinstance(e, LogEntry)]

    if not regular_hot:
        return

    entries_text = "\n".join(
        f"- [{e.source_id} {e.start_offset}-{e.end_offset}s] {e.note}"
        for e in regular_hot
    )
    response = litellm.completion(
        model=model,
        messages=[
            {
                "role": "user",
                "content": (
                    "Summarize these memory log entries as a concise arc summary (2-4 sentences). "
                    "Focus on how this topic evolved, key changes, emotional trajectory, and current state:\n\n"
                    f"{entries_text}"
                ),
            }
        ],
    )
    fence_note = response.choices[0].message.content.strip()

    timestamps = [e.timestamp for e in regular_hot]
    fence = FenceEntry(
        is_fence=True,
        timestamp=datetime.now(tz=timezone.utc),
        note=fence_note,
        entries_behind=len(regular_hot),
        date_range=(min(timestamps), max(timestamps)),
    )
    fence_json = _serialize_log_entry(fence)
    graph.query(
        "MATCH (n:SemanticNode {id: $id}) SET n.log = n.log + [$fence_json]",
        {"id": node_id, "fence_json": fence_json},
    )


def run_fence_checks(
    graph: Graph, touched_node_ids: list[str], log_token_budget: int, model: str
) -> None:
    """Check each touched node; create a fence if the hot segment exceeds the budget."""
    for node_id in touched_node_ids:
        try:
            node_output = get_node(graph, node_id)
        except ValueError:
            continue  # node was deleted during the session

        _, _, hot = _split_log(node_output.node.log)
        regular_hot = [e for e in hot if isinstance(e, LogEntry)]
        if _hot_segment_token_count(regular_hot) > log_token_budget:
            create_fence(graph, node_id, model, node_output=node_output)


def get_cold_logs(graph: Graph, node_id: str) -> GetColdLogsOutput:
    result = graph.query(
        "MATCH (n:SemanticNode {id: $id}) RETURN n.log",
        {"id": node_id},
    )
    if not result.result_set:
        raise ValueError(f"SemanticNode '{node_id}' not found.")

    raw_log = result.result_set[0][0] or []
    all_entries = [_deserialize_log_entry(s) for s in raw_log]
    cold, last_fence, _hot = _split_log(all_entries)

    # cold = everything before the last fence; include last_fence too for full cold view
    cold_entries: list[LogEntry | FenceEntry] = list(cold)
    if last_fence is not None:
        cold_entries.append(last_fence)

    return GetColdLogsOutput(entries=cold_entries)
