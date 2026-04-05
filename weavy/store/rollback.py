"""
Ingestion rollback — reverse all graph mutations caused by a transcript ingestion run.

Usage:
    from weavy.store.rollback import rollback_ingestion
    rollback_ingestion("rec:3")

After a successful rollback the transcript's ingestion_status is reset to 0
and its run_manifest is cleared, making the transcript eligible for re-ingestion.
"""

from falkordb import Graph

from weavy.config import settings
from weavy.models.traces import EdgeSnapshot, MutationOp, NodeSnapshot
from weavy.store import canonical as store_canonical
from weavy.store.client import get_graph
from weavy.store.graph import generate_embedding as _generate_embedding_strict


def _generate_embedding(aliases: list[str], summary: str) -> list[float] | None:
    try:
        return _generate_embedding_strict(aliases, summary)
    except Exception:
        return None


def _apply_node_snapshot(graph: Graph, snap: NodeSnapshot) -> None:
    """Overwrite a node's mutable properties with the snapshot state."""
    embedding = _generate_embedding(snap.aliases, snap.summary)
    params: dict = {
        "id": snap.id,
        "name": snap.name,
        "aliases": snap.aliases,
        "summary": snap.summary,
        "log": snap.log,
        "total_log_count": snap.total_log_count,
    }
    if embedding is not None:
        params["embedding"] = embedding
        graph.query(
            """
            MATCH (n:SemanticNode {id: $id})
            SET n.name = $name, n.aliases = $aliases, n.summary = $summary,
                n.log = $log, n.total_log_count = $total_log_count,
                n.embedding = vecf32($embedding)
            """,
            params,
        )
    else:
        graph.query(
            """
            MATCH (n:SemanticNode {id: $id})
            SET n.name = $name, n.aliases = $aliases, n.summary = $summary,
                n.log = $log, n.total_log_count = $total_log_count
            """,
            params,
        )


def _recreate_node(graph: Graph, snap: NodeSnapshot) -> None:
    """Recreate a deleted node from its snapshot, including its edges."""
    graph.query(
        """
        CREATE (n:SemanticNode {
            id: $id, name: $name, aliases: $aliases,
            summary: $summary, log: $log, total_log_count: $total_log_count
        })
        """,
        {
            "id": snap.id,
            "name": snap.name,
            "aliases": snap.aliases,
            "summary": snap.summary,
            "log": snap.log,
            "total_log_count": snap.total_log_count,
        },
    )
    embedding = _generate_embedding(snap.aliases, snap.summary)
    if embedding is not None:
        graph.query(
            "MATCH (n:SemanticNode {id: $id}) SET n.embedding = vecf32($embedding)",
            {"id": snap.id, "embedding": embedding},
        )
    # Recreate edges that were destroyed by DETACH DELETE.
    # Only recreate edges where both endpoints currently exist to avoid orphan edges.
    for edge in snap.edges:
        result = graph.query(
            """
            MATCH (a:SemanticNode {id: $from_id}), (b:SemanticNode {id: $to_id})
            RETURN 1
            """,
            {"from_id": edge.from_node_id, "to_id": edge.to_node_id},
        )
        if result.result_set:
            graph.query(
                """
                MATCH (a:SemanticNode {id: $from_id}), (b:SemanticNode {id: $to_id})
                CREATE (a)-[:RELATES {id: $edge_id, label: $label}]->(b)
                """,
                {
                    "from_id": edge.from_node_id,
                    "to_id": edge.to_node_id,
                    "edge_id": edge.id,
                    "label": edge.label,
                },
            )


def _node_exists(graph: Graph, node_id: str) -> bool:
    return bool(
        graph.query(
            "MATCH (n:SemanticNode {id: $id}) RETURN 1",
            {"id": node_id},
        ).result_set
    )


def _edge_exists(graph: Graph, edge_id: str) -> bool:
    return bool(
        graph.query(
            "MATCH ()-[r:RELATES {id: $id}]->() RETURN 1",
            {"id": edge_id},
        ).result_set
    )


def rollback_ingestion(transcript_id: str) -> None:
    """Reverse all graph mutations recorded in the transcript's run manifest.

    Operations are applied in reverse order so that each undo correctly
    mirrors the original sequence. On success the transcript's
    ingestion_status is reset to 0 and the run_manifest is cleared.

    Raises ValueError if the transcript has no manifest (never ingested or
    already rolled back).
    """
    graph = get_graph(settings.GRAPH_NAME)

    ops = store_canonical.get_run_manifest(graph, transcript_id)
    if ops is None:
        # No manifest means ingestion either never completed or was already rolled back.
        # Reset the flag unconditionally so the transcript can be re-ingested.
        store_canonical.set_ingestion_status(graph, transcript_id, 0)
        return

    for op in reversed(ops):
        _apply_op_rollback(graph, op)

    store_canonical.clear_run_manifest(graph, transcript_id)
    store_canonical.set_ingestion_status(graph, transcript_id, 0)


def _apply_op_rollback(graph: Graph, op: MutationOp) -> None:
    if op.op == "create_node":
        assert op.node_id is not None
        graph.query(
            "MATCH (n:SemanticNode {id: $id}) DETACH DELETE n",
            {"id": op.node_id},
        )

    elif op.op == "update_node":
        assert op.node_before is not None
        if _node_exists(graph, op.node_before.id):
            _apply_node_snapshot(graph, op.node_before)

    elif op.op == "delete_node":
        assert op.node_before is not None
        if _node_exists(graph, op.node_before.id):
            # Node was re-created by an earlier rollback step (e.g. reversed create_node
            # in the same run that first created then deleted it) — just restore state.
            _apply_node_snapshot(graph, op.node_before)
        else:
            _recreate_node(graph, op.node_before)

    elif op.op == "create_edge":
        assert op.edge_id is not None
        graph.query(
            "MATCH ()-[r:RELATES {id: $id}]->() DELETE r",
            {"id": op.edge_id},
        )

    elif op.op == "update_edge":
        assert op.edge_before is not None
        if _edge_exists(graph, op.edge_before.id):
            graph.query(
                "MATCH ()-[r:RELATES {id: $id}]->() SET r.label = $label",
                {"id": op.edge_before.id, "label": op.edge_before.label},
            )

    elif op.op == "delete_edge":
        assert op.edge_before is not None
        snap: EdgeSnapshot = op.edge_before
        if not _edge_exists(graph, snap.id):
            graph.query(
                """
                MATCH (a:SemanticNode {id: $from_id}), (b:SemanticNode {id: $to_id})
                CREATE (a)-[:RELATES {id: $edge_id, label: $label}]->(b)
                """,
                {
                    "from_id": snap.from_node_id,
                    "to_id": snap.to_node_id,
                    "edge_id": snap.id,
                    "label": snap.label,
                },
            )
