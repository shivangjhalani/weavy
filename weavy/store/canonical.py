"""
Canonical source persistence — Transcript and ChatSession CRUD in FalkorDB.
"""

import json
import re
from datetime import datetime

from falkordb import Graph

from weavy.models.canonical import ChatMessage, ChatSession, Transcript
from weavy.models.traces import EdgeSnapshot, MutationOp, NodeSnapshot
from weavy.models.tools import (
    ChatSummary,
    GetChatOutput,
    GetTranscriptSpanResult,
    ListChatsInput,
    ListChatsOutput,
    ListTranscriptsInput,
    ListTranscriptsOutput,
    TranscriptSummary,
)

_INLINE_TS = re.compile(r"^\[(\d+):(\d{2})\]")


def _extract_span(text: str, start_offset: int, end_offset: int) -> str:
    """
    Return lines whose inline [M:SS] timestamp falls within [start_offset, end_offset].
    If the text contains no inline timestamps, return the full text unchanged.
    """
    lines = text.splitlines()
    has_timestamps = any(_INLINE_TS.match(line) for line in lines)
    if not has_timestamps:
        return text

    current_seconds: int | None = None
    result: list[str] = []
    for line in lines:
        match = _INLINE_TS.match(line)
        if match:
            current_seconds = int(match.group(1)) * 60 + int(match.group(2))
        if current_seconds is not None and start_offset <= current_seconds <= end_offset:
            result.append(line)
    return "\n".join(result)


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------


def create_transcript(graph: Graph, transcript: Transcript) -> None:
    graph.query(
        """
        CREATE (t:Transcript {
            id: $id,
            name: $id,
            audio_path: $audio_path,
            timestamp: $timestamp,
            text: $text,
            ingestion_status: 0
        })
        """,
        {
            "id": transcript.id,
            "audio_path": transcript.audio_path,
            "timestamp": transcript.timestamp.isoformat(),
            "text": transcript.text,
        },
    )


def get_transcript(graph: Graph, transcript_id: str) -> Transcript:
    result = graph.query(
        "MATCH (t:Transcript {id: $id}) RETURN t",
        {"id": transcript_id},
    )
    if not result.result_set:
        raise ValueError(f"Transcript '{transcript_id}' not found.")
    props = result.result_set[0][0].properties
    return Transcript(
        id=props["id"],
        audio_path=props["audio_path"],
        timestamp=datetime.fromisoformat(props["timestamp"]),
        text=props["text"],
    )


def list_transcripts(graph: Graph, params: ListTranscriptsInput) -> ListTranscriptsOutput:
    if params.date_range:
        start, end = params.date_range
        result = graph.query(
            """
            MATCH (t:Transcript)
            WHERE t.timestamp >= $start AND t.timestamp <= $end
            RETURN t
            ORDER BY t.timestamp DESC
            LIMIT $limit
            """,
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": params.limit,
            },
        )
    else:
        result = graph.query(
            "MATCH (t:Transcript) RETURN t ORDER BY t.timestamp DESC LIMIT $limit",
            {"limit": params.limit},
        )
    transcripts = []
    for row in result.result_set:
        props = row[0].properties
        transcripts.append(
            TranscriptSummary(
                id=props["id"],
                timestamp=datetime.fromisoformat(props["timestamp"]),
                audio_path=props["audio_path"],
            )
        )
    return ListTranscriptsOutput(transcripts=transcripts)


def get_transcript_span(
    graph: Graph, transcript_id: str, start_offset: int, end_offset: int
) -> GetTranscriptSpanResult:
    transcript = get_transcript(graph, transcript_id)
    text = _extract_span(transcript.text, start_offset, end_offset)
    return GetTranscriptSpanResult(transcript_id=transcript_id, text=text)


# ---------------------------------------------------------------------------
# ChatSession
# ---------------------------------------------------------------------------


def create_chat_session(graph: Graph, session: ChatSession) -> None:
    messages_json = json.dumps([m.model_dump() for m in session.messages])
    graph.query(
        """
        CREATE (c:ChatSession {
            id: $id,
            name: $id,
            timestamp: $timestamp,
            messages: $messages
        })
        """,
        {
            "id": session.id,
            "timestamp": session.timestamp.isoformat(),
            "messages": messages_json,
        },
    )


def get_chat_session(graph: Graph, chat_id: str) -> ChatSession:
    result = graph.query(
        "MATCH (c:ChatSession {id: $id}) RETURN c",
        {"id": chat_id},
    )
    if not result.result_set:
        raise ValueError(f"ChatSession '{chat_id}' not found.")
    props = result.result_set[0][0].properties
    messages = [ChatMessage(**m) for m in json.loads(props["messages"])]
    return ChatSession(
        id=props["id"],
        timestamp=datetime.fromisoformat(props["timestamp"]),
        messages=messages,
    )


def list_chats(graph: Graph, params: ListChatsInput) -> ListChatsOutput:
    if params.date_range:
        start, end = params.date_range
        result = graph.query(
            """
            MATCH (c:ChatSession)
            WHERE c.timestamp >= $start AND c.timestamp <= $end
            RETURN c
            ORDER BY c.timestamp DESC
            LIMIT $limit
            """,
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": params.limit,
            },
        )
    else:
        result = graph.query(
            "MATCH (c:ChatSession) RETURN c ORDER BY c.timestamp DESC LIMIT $limit",
            {"limit": params.limit},
        )
    chats = []
    for row in result.result_set:
        props = row[0].properties
        chats.append(
            ChatSummary(
                id=props["id"],
                timestamp=datetime.fromisoformat(props["timestamp"]),
            )
        )
    return ListChatsOutput(chats=chats)


def get_chat(
    graph: Graph, chat_id: str, start_index: int | None, end_index: int | None
) -> GetChatOutput:
    session = get_chat_session(graph, chat_id)
    messages = session.messages[start_index:end_index]
    return GetChatOutput(
        session=ChatSession(
            id=session.id,
            timestamp=session.timestamp,
            messages=messages,
        )
    )


# ---------------------------------------------------------------------------
# Ingestion status and run manifest (Transcript nodes)
# ---------------------------------------------------------------------------


def get_ingestion_status(graph: Graph, transcript_id: str) -> int:
    """Return 0 (not ingested) or 1 (ingested / in-progress). Raises if transcript not found."""
    result = graph.query(
        "MATCH (t:Transcript {id: $id}) RETURN coalesce(t.ingestion_status, 0)",
        {"id": transcript_id},
    )
    if not result.result_set:
        raise ValueError(f"Transcript '{transcript_id}' not found.")
    return int(result.result_set[0][0])


def set_ingestion_status(graph: Graph, transcript_id: str, status: int) -> None:
    graph.query(
        "MATCH (t:Transcript {id: $id}) SET t.ingestion_status = $status",
        {"id": transcript_id, "status": status},
    )


def save_run_manifest(graph: Graph, transcript_id: str, ops: list[MutationOp]) -> None:
    """Persist the ordered list of mutation ops as JSON on the Transcript node."""
    manifest_json = json.dumps([op.model_dump() for op in ops])
    graph.query(
        "MATCH (t:Transcript {id: $id}) SET t.run_manifest = $manifest",
        {"id": transcript_id, "manifest": manifest_json},
    )


def get_run_manifest(graph: Graph, transcript_id: str) -> list[MutationOp] | None:
    """Load and deserialize the run manifest. Returns None if no manifest is stored."""
    result = graph.query(
        "MATCH (t:Transcript {id: $id}) RETURN t.run_manifest",
        {"id": transcript_id},
    )
    if not result.result_set:
        raise ValueError(f"Transcript '{transcript_id}' not found.")
    manifest_json = result.result_set[0][0]
    if not manifest_json:
        return None
    return [_deserialize_mutation_op(d) for d in json.loads(manifest_json)]


def clear_run_manifest(graph: Graph, transcript_id: str) -> None:
    graph.query(
        "MATCH (t:Transcript {id: $id}) REMOVE t.run_manifest",
        {"id": transcript_id},
    )


def _deserialize_mutation_op(data: dict) -> MutationOp:
    """Reconstruct a MutationOp, inferring the before-image type from the op name."""
    op = data["op"]
    node_before = None
    edge_before = None

    if op in ("update_node", "delete_node") and data.get("node_before"):
        b = data["node_before"]
        edges = [EdgeSnapshot(**e) for e in (b.get("edges") or [])]
        node_before = NodeSnapshot(**{**b, "edges": edges})
    elif op in ("update_edge", "delete_edge") and data.get("edge_before"):
        edge_before = EdgeSnapshot(**data["edge_before"])

    return MutationOp(
        op=op,
        node_id=data.get("node_id"),
        edge_id=data.get("edge_id"),
        node_before=node_before,
        edge_before=edge_before,
    )
