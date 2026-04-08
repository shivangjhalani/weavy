"""
Canonical source persistence — Transcript and ChatSession CRUD in FalkorDB.
"""

import json
from datetime import datetime

from falkordb import Graph

from weavy.models.canonical import (
    ChatMessage,
    ChatSession,
    Transcript,
    TranscriptSegment,
    extract_transcript_span,
)
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

# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------


def create_transcript(graph: Graph, transcript: Transcript) -> None:
    segments_json = json.dumps([s.model_dump() for s in transcript.segments])
    graph.query(
        """
        CREATE (t:Transcript {
            id: $id,
            name: $id,
            audio_path: $audio_path,
            timestamp: $timestamp,
            segments: $segments,
            ingestion_state: 'pending'
        })
        """,
        {
            "id": transcript.id,
            "audio_path": transcript.audio_path,
            "timestamp": transcript.timestamp.isoformat(),
            "segments": segments_json,
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
    segments = [TranscriptSegment(**s) for s in json.loads(props["segments"])]
    return Transcript(
        id=props["id"],
        audio_path=props["audio_path"],
        timestamp=datetime.fromisoformat(props["timestamp"]),
        segments=segments,
    )


def list_transcripts(
    graph: Graph, params: ListTranscriptsInput
) -> ListTranscriptsOutput:
    if params.date_range:
        start, end = params.date_range
        result = graph.query(
            """
            MATCH (t:Transcript)
            WHERE t.timestamp >= $start AND t.timestamp <= $end
            RETURN t.id, t.timestamp
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
            "MATCH (t:Transcript) RETURN t.id, t.timestamp ORDER BY t.timestamp DESC LIMIT $limit",
            {"limit": params.limit},
        )
    transcripts = [
        TranscriptSummary(
            id=row[0],
            timestamp=datetime.fromisoformat(row[1]),
        )
        for row in result.result_set
    ]
    return ListTranscriptsOutput(transcripts=transcripts)


def get_transcript_span(
    graph: Graph,
    transcript_id: str,
    start_offset: float,
    end_offset: float,
    context_secs: float = 0,
) -> GetTranscriptSpanResult:
    transcript = get_transcript(graph, transcript_id)
    text = extract_transcript_span(
        transcript.segments,
        start_offset,
        end_offset,
        context_secs,
    )
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
            RETURN c.id, c.timestamp
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
            "MATCH (c:ChatSession) RETURN c.id, c.timestamp ORDER BY c.timestamp DESC LIMIT $limit",
            {"limit": params.limit},
        )
    chats = [
        ChatSummary(
            id=row[0],
            timestamp=datetime.fromisoformat(row[1]),
        )
        for row in result.result_set
    ]
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
# Ingestion state (Transcript nodes)
# ---------------------------------------------------------------------------


def get_ingestion_state(graph: Graph, transcript_id: str) -> str:
    result = graph.query(
        "MATCH (t:Transcript {id: $id}) RETURN t.ingestion_state",
        {"id": transcript_id},
    )
    if not result.result_set:
        raise ValueError(f"Transcript '{transcript_id}' not found.")
    return str(result.result_set[0][0])


def set_ingestion_state(
    graph: Graph,
    transcript_id: str,
    state: str,
) -> None:
    graph.query(
        "MATCH (t:Transcript {id: $id}) SET t.ingestion_state = $state",
        {"id": transcript_id, "state": state},
    )
