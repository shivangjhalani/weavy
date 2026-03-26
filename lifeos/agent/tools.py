"""build_tools factory — returns 9 agent tool callables and OpenAI-format declarations.

Each tool is a closure over the graph and store objects, bridging the agent's
LLM decisions to graph.py operations.

Usage:
    tools_dict, declarations = build_tools(graph, store, recording_timestamp=ts)
    harness = AgentHarness(model=..., tools=tools_dict, declarations=declarations)
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from lifeos.memory import graph as graph_module
from lifeos.memory.models import Edge, EpisodeSpan, LogEntry, Node, TranscriptRef
from lifeos.memory.store import TranscriptStore
from lifeos.core.embeddings import embed_text


def build_tools(
    graph: Any,
    store: TranscriptStore,
    recording_timestamp: datetime | None = None,
) -> tuple[dict, list]:
    """Build and return the 9 ingestion agent tools.

    Args:
        graph: FalkorDB graph object (from init_graph).
        store: TranscriptStore instance for episode span persistence.
        recording_timestamp: Optional datetime for log entries; defaults to now
            if not provided. Pass the recording time of the audio file.

    Returns:
        (tools_dict, declarations_list) where tools_dict maps tool name to
        callable and declarations_list contains 9 OpenAI-format tool dicts.
    """

    def _ts() -> datetime:
        """Return recording_timestamp if set, else current UTC time."""
        return recording_timestamp if recording_timestamp is not None else datetime.now(timezone.utc)

    def _make_refs(
        transcript_id: str | None,
        start_offset: int | None,
        end_offset: int | None,
    ) -> list[TranscriptRef]:
        """Build a refs list from optional transcript coordinates."""
        if transcript_id is None:
            return []
        return [TranscriptRef(
            transcript_id=transcript_id,
            start_offset=start_offset,
            end_offset=end_offset,
        )]

    # -----------------------------------------------------------------------
    # Tool 1: search_nodes_by_alias
    # -----------------------------------------------------------------------

    def search_nodes_by_alias(alias: str) -> dict:
        """Find nodes whose aliases list contains the given alias (exact match)."""
        results = graph_module.search_nodes_by_alias(graph, alias)
        return {"matches": results, "count": len(results)}

    # -----------------------------------------------------------------------
    # Tool 2: search_nodes_by_embedding
    # -----------------------------------------------------------------------

    def search_nodes_by_embedding(query: str, k: int = 5) -> dict:
        """Semantic similarity search over node summaries using vector index."""
        results = graph_module.vector_search(graph, query, k=k)
        return {
            "matches": [
                {"node_id": r[0], "summary": r[1], "score": r[2]}
                for r in results
            ]
        }

    # -----------------------------------------------------------------------
    # Tool 3: create_node
    # -----------------------------------------------------------------------

    def create_node(
        name: str,
        summary: str,
        aliases: list[str] | None = None,
        log_note: str | None = None,
        transcript_id: str | None = None,
        start_offset: int | None = None,
        end_offset: int | None = None,
    ) -> dict:
        """Create a new node in the graph with a generated UUID."""
        node_id = str(uuid.uuid4())
        node_aliases = aliases if aliases is not None else [name]
        refs = _make_refs(transcript_id, start_offset, end_offset)
        log: list[LogEntry] = []
        if log_note is not None:
            log.append(LogEntry(recorded_at=_ts(), note=log_note))
        node = Node(
            id=node_id,
            name=name,
            summary=summary,
            aliases=node_aliases,
            log=log,
            refs=refs,
        )
        graph_module.create_node(graph, node)
        return {"node_id": node_id, "created": True}

    # -----------------------------------------------------------------------
    # Tool 4: update_node
    # -----------------------------------------------------------------------

    def update_node(
        node_id: str,
        summary: str,
        log_note: str,
        new_aliases: list[str] | None = None,
        transcript_id: str | None = None,
        start_offset: int | None = None,
        end_offset: int | None = None,
    ) -> dict:
        """Update an existing node's summary, log, and optionally aliases/refs."""
        new_refs = _make_refs(transcript_id, start_offset, end_offset) or None
        graph_module.update_node(
            graph,
            node_id,
            summary,
            log_note,
            new_aliases=new_aliases,
            new_refs=new_refs,
            recorded_at=_ts(),
        )
        return {"node_id": node_id, "updated": True}

    # -----------------------------------------------------------------------
    # Tool 5: delete_node
    # -----------------------------------------------------------------------

    def delete_node(node_id: str) -> dict:
        """Delete a node and all its relationships from the graph."""
        graph_module.delete_node(graph, node_id)
        return {"node_id": node_id, "deleted": True}

    # -----------------------------------------------------------------------
    # Tool 6: create_edge
    # -----------------------------------------------------------------------

    def create_edge(
        source_id: str,
        target_id: str,
        label: str,
        summary: str,
        log_note: str | None = None,
        transcript_id: str | None = None,
        start_offset: int | None = None,
        end_offset: int | None = None,
    ) -> dict:
        """Create a directed edge between two nodes in the graph."""
        edge_id = str(uuid.uuid4())
        refs = _make_refs(transcript_id, start_offset, end_offset)
        log: list[LogEntry] = []
        if log_note is not None:
            log.append(LogEntry(recorded_at=_ts(), note=log_note))
        edge = Edge(
            id=edge_id,
            label=label,
            source_id=source_id,
            target_id=target_id,
            summary=summary,
            log=log,
            refs=refs,
        )
        graph_module.create_edge(graph, edge)
        return {"edge_id": edge_id, "created": True}

    # -----------------------------------------------------------------------
    # Tool 7: update_edge
    # -----------------------------------------------------------------------

    def update_edge(
        edge_id: str,
        summary: str,
        log_note: str,
        transcript_id: str | None = None,
        start_offset: int | None = None,
        end_offset: int | None = None,
    ) -> dict:
        """Update an existing edge's summary and log."""
        new_refs = _make_refs(transcript_id, start_offset, end_offset) or None
        graph_module.update_edge(
            graph,
            edge_id,
            summary,
            log_note,
            new_refs=new_refs,
            recorded_at=_ts(),
        )
        return {"edge_id": edge_id, "updated": True}

    # -----------------------------------------------------------------------
    # Tool 8: delete_edge
    # -----------------------------------------------------------------------

    def delete_edge(edge_id: str) -> dict:
        """Delete an edge from the graph by its id."""
        graph_module.delete_edge(graph, edge_id)
        return {"edge_id": edge_id, "deleted": True}

    # -----------------------------------------------------------------------
    # Tool 9: create_episode_spans
    # -----------------------------------------------------------------------

    def create_episode_spans(transcript_id: str, spans: list[dict]) -> dict:
        """Add episode spans to a transcript, embedding each span summary.

        Loads the transcript from store, appends EpisodeSpan objects with
        embeddings to the episode_spans list, and saves back.
        """
        data = store.load(transcript_id) or {"id": transcript_id, "episode_spans": []}
        if "episode_spans" not in data:
            data["episode_spans"] = []

        for span in spans:
            episode_span = EpisodeSpan(
                start_offset=span["start_offset"],
                end_offset=span["end_offset"],
                summary=span["summary"],
                embedding=embed_text(span["summary"]),
            )
            data["episode_spans"].append(episode_span.model_dump(mode="json"))

        store.save(transcript_id, data)
        return {"transcript_id": transcript_id, "spans_created": len(spans)}

    # -----------------------------------------------------------------------
    # Tool dict
    # -----------------------------------------------------------------------

    tools_dict = {
        "search_nodes_by_alias": search_nodes_by_alias,
        "search_nodes_by_embedding": search_nodes_by_embedding,
        "create_node": create_node,
        "update_node": update_node,
        "delete_node": delete_node,
        "create_edge": create_edge,
        "update_edge": update_edge,
        "delete_edge": delete_edge,
        "create_episode_spans": create_episode_spans,
    }

    # -----------------------------------------------------------------------
    # OpenAI-format tool declarations — plain Python dicts (no SDK imports)
    # -----------------------------------------------------------------------

    # Reusable optional transcript coordinate properties
    _transcript_props = {
        "transcript_id": {"type": "string"},
        "start_offset": {"type": "integer"},
        "end_offset": {"type": "integer"},
    }

    declarations = [
        {
            "type": "function",
            "function": {
                "name": "search_nodes_by_alias",
                "description": "Find graph nodes whose alias set contains the given alias (exact match). Use this as the first disambiguation step before creating a new node.",
                "parameters": {
                    "type": "object",
                    "properties": {"alias": {"type": "string"}},
                    "required": ["alias"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_nodes_by_embedding",
                "description": "Semantic similarity search over node summaries using vector KNN. Use as second disambiguation step when alias search returns no results. Returns nodes with similarity scores.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "k": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_node",
                "description": "Create a new node in the semantic graph. Only call after confirming via search that no existing node represents this entity. Only persist things that matter to the person's evolving inner life.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "summary": {"type": "string"},
                        "aliases": {"type": "array", "items": {"type": "string"}},
                        "log_note": {"type": "string"},
                        **_transcript_props,
                    },
                    "required": ["name", "summary"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_node",
                "description": "Update an existing node's summary and append a log entry. Use when an entity already exists and new information changes or extends its description.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string"},
                        "summary": {"type": "string"},
                        "log_note": {"type": "string"},
                        "new_aliases": {"type": "array", "items": {"type": "string"}},
                        **_transcript_props,
                    },
                    "required": ["node_id", "summary", "log_note"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_node",
                "description": "Delete a node and all its relationships from the graph. Use when an entity is no longer relevant or was created in error.",
                "parameters": {
                    "type": "object",
                    "properties": {"node_id": {"type": "string"}},
                    "required": ["node_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_edge",
                "description": "Create a directed relationship edge between two existing nodes. The label is a concise descriptor (e.g. 'fears', 'is_mentor_of', 'evolved_into').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string"},
                        "target_id": {"type": "string"},
                        "label": {"type": "string"},
                        "summary": {"type": "string"},
                        "log_note": {"type": "string"},
                        **_transcript_props,
                    },
                    "required": ["source_id", "target_id", "label", "summary"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_edge",
                "description": "Update an existing edge's summary and append a log entry. Use when a relationship has evolved or new information changes its description.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "edge_id": {"type": "string"},
                        "summary": {"type": "string"},
                        "log_note": {"type": "string"},
                        **_transcript_props,
                    },
                    "required": ["edge_id", "summary", "log_note"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_edge",
                "description": "Delete a relationship edge from the graph by its id.",
                "parameters": {
                    "type": "object",
                    "properties": {"edge_id": {"type": "string"}},
                    "required": ["edge_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_episode_spans",
                "description": "Store episode spans for a transcript. Call after all graph writes are complete to mark significant segments with start/end offsets and summaries.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "transcript_id": {"type": "string"},
                        "spans": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "start_offset": {"type": "integer"},
                                    "end_offset": {"type": "integer"},
                                    "summary": {"type": "string"},
                                },
                                "required": ["start_offset", "end_offset", "summary"],
                            },
                        },
                    },
                    "required": ["transcript_id", "spans"],
                },
            },
        },
    ]

    return tools_dict, declarations
