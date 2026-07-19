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
from weavy.store import canonical as store_canonical
from weavy.store import graph as store_graph
from weavy.store import system as store_system

# Cosine distance below which a prospective node is treated as an existing
# entity. Deliberately tight: in the 0.3–0.4 band same-entity and
# distinct-entity pairs overlap (summaries describe content, not identity), so
# the vector check only catches near-certain rephrasings; alias equality is the
# primary identity signal and is checked independently of distance.
#
# Compared against identity_embedding (aliases+summary only — see
# find_similar_nodes), never the content embedding that accumulates note
# history, so the comparison is always apples-to-apples regardless of how many
# times the existing node has been updated. This is an irreducible judgment
# call, not a derivable fact — it is scoped to the embedding model actually
# configured (settings.EMBEDDING_MODEL), not assumed universal across models.
DUPLICATE_DISTANCE = 0.2

# Episode chunking: greedy line packing into windows of roughly this many
# characters, overlapping by one line so facts straddling a boundary survive.
# This is a retrieval-granularity target, not a derivable value — but it must
# never exceed what the embedding model can actually take, so chunk_text clamps
# it against the model's real budget rather than trusting the guess blindly.
_CHUNK_TARGET_CHARS = 800


def chunk_text(text: str, target: int | None = None) -> list[str]:
    """Split text into overlapping windows for embedding, structure-agnostic.

    Lines are the packing unit when present (dialogue, notes, logs); a single
    line longer than *target* is hard-split. Consecutive chunks share one line
    of overlap. *target* defaults to the smaller of the quality target and the
    embedding model's real capacity, computed lazily so it stays mockable in
    tests instead of being frozen in a default argument at import time.
    """
    if target is None:
        target = min(_CHUNK_TARGET_CHARS, embedding.get_char_budget())
    units: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        while len(line) > target:
            units.append(line[:target])
            line = line[target:]
        if line:
            units.append(line)
    if not units:
        return []

    chunks: list[str] = []
    window: list[str] = []
    size = 0
    for unit in units:
        if window and size + len(unit) > target:
            chunks.append("\n".join(window))
            # one-line overlap, skipped when it would blow the target
            carry = window[-1]
            window = [carry] if len(carry) + len(unit) <= target else []
            size = sum(len(u) for u in window)
        window.append(unit)
        size += len(unit)
    if window:
        chunks.append("\n".join(window))
    return chunks


def index_episode(
    graph: Graph, *, session_id: str, text: str, timestamp: datetime
) -> None:
    """Embed an episode's text as chunks so search can surface source excerpts."""
    chunks = chunk_text(text)
    if not chunks:
        return
    vectors = [embedding.embed(c) for c in chunks]
    store_canonical.create_chunks(graph, session_id, chunks, vectors, timestamp)


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
    force: bool = False,
) -> OperationResult:
    vec = embedding.embed_node(aliases, summary)

    # One node per entity is a storage invariant, not a prompt convention:
    # refuse writes that collide with an existing entity unless forced.
    if not force:
        similar = store_graph.find_similar_nodes(
            graph, aliases=aliases, embedding=vec, max_distance=DUPLICATE_DISTANCE
        )
        if similar:
            listing = ", ".join(
                f"{nid} ({alias!r}, distance {dist:.2f})"
                for nid, alias, dist in similar
            )
            return OperationResult(
                ok=False,
                message=(
                    f"Not created — existing node(s) likely denote this entity: "
                    f"{listing}. Call update_node on the match instead. If this "
                    f"truly is a distinct entity, retry with force=true."
                ),
            )

    node_id = store_system.increment_counter(graph, "node")
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
    # Every update re-embeds the node over its accumulated knowledge —
    # aliases, current summary, and the trail of log notes (which hold each
    # archived summary) — so facts stay retrievable after the summary moves on.
    current = store_graph.get_node(graph, node_id)
    fetched_summary = current.node.summary
    aliases = new_aliases if new_aliases is not None else current.node.aliases
    summary = new_summary if new_summary is not None else fetched_summary
    notes = [entry.note for entry in current.node.log] + [note]
    vec = embedding.embed_node(aliases, summary, notes)

    # identity_embedding (aliases+summary only, no notes) is dedup's own,
    # stable representation — recomputed only when the identity-relevant
    # fields actually change, not on every log entry.
    identity_vec = (
        embedding.embed_node(aliases, summary)
        if new_summary is not None or new_aliases is not None
        else None
    )

    result = store_graph.update_node(
        graph,
        node_id=node_id,
        note=note,
        new_summary=new_summary,
        new_aliases=new_aliases,
        provenance=provenance,
        identity_embedding=identity_vec,
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
    if result.ok:
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
