"""
Canonical source persistence — Session CRUD in FalkorDB.
"""

import json
from datetime import datetime

from falkordb import Graph
from pydantic import BaseModel

from weavy.models.canonical import (
    ChatMessage,
    Session,
)
from weavy.models.tools import (
    GetSessionOutput,
    ListSessionsInput,
    ListSessionsOutput,
    SessionSummary,
)


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


def create_session(graph: Graph, session: Session) -> None:
    messages_json = json.dumps([m.model_dump() for m in session.messages])
    graph.query(
        """
        CREATE (s:Session {
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


def get_session(
    graph: Graph, session_id: str, *, check_completed: bool = False
) -> Session:
    result = graph.query(
        "MATCH (s:Session {id: $id}) RETURN s",
        {"id": session_id},
    )
    if not result.result_set:
        raise ValueError(f"Session '{session_id}' not found.")
    props = result.result_set[0][0].properties
    if check_completed and props.get("completed_at") is not None:
        raise ValueError(f"Session '{session_id}' is already completed.")
    messages = [ChatMessage(**m) for m in json.loads(props["messages"])]
    return Session(
        id=props["id"],
        timestamp=datetime.fromisoformat(props["timestamp"]),
        messages=messages,
    )


def list_sessions(graph: Graph, params: ListSessionsInput) -> ListSessionsOutput:
    if params.date_range:
        start, end = params.date_range
        result = graph.query(
            """
            MATCH (s:Session)
            WHERE s.timestamp >= $start AND s.timestamp <= $end
            RETURN s.id, s.timestamp, s.summary
            ORDER BY s.timestamp DESC
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
            "MATCH (s:Session) RETURN s.id, s.timestamp, s.summary ORDER BY s.timestamp DESC LIMIT $limit",
            {"limit": params.limit},
        )
    sessions = [
        SessionSummary(
            id=row[0],
            timestamp=datetime.fromisoformat(row[1]),
            summary=row[2],
        )
        for row in result.result_set
    ]
    return ListSessionsOutput(sessions=sessions)


def get_session_messages(
    graph: Graph,
    session_id: str,
    start_index: int | None,
    end_index: int | None,
    max_chars: int = 6000,
) -> GetSessionOutput:
    session = get_session(graph, session_id)
    messages = session.messages[start_index:end_index]
    # Drop oldest messages until total content fits within max_chars
    total = sum(len(m.content) for m in messages)
    while len(messages) > 1 and total > max_chars:
        total -= len(messages[0].content)
        messages = messages[1:]
    return GetSessionOutput(
        session=Session(
            id=session.id,
            timestamp=session.timestamp,
            messages=messages,
        )
    )


# ---------------------------------------------------------------------------
# Session outcomes (written after agent processing)
# ---------------------------------------------------------------------------


def get_session_graph_changes(graph: Graph, session_id: str) -> dict:
    """Read existing graph_changes from a session, or {} if not yet set."""
    result = graph.query(
        "MATCH (s:Session {id: $id}) RETURN s.graph_changes",
        {"id": session_id},
    )
    if not result.result_set or not result.result_set[0][0]:
        return {}
    return json.loads(result.result_set[0][0])


def persist_session_outcomes(
    graph: Graph,
    session_id: str,
    summary: str,
    graph_changes: dict,
    completed_at: str,
) -> None:
    """Write processing outcomes onto a Session node."""
    graph.query(
        """
        MATCH (s:Session {id: $id})
        SET s.summary = $summary,
            s.graph_changes = $graph_changes,
            s.completed_at = $completed_at
        """,
        {
            "id": session_id,
            "summary": summary,
            "graph_changes": json.dumps(graph_changes),
            "completed_at": completed_at,
        },
    )


def get_session_raw_messages(graph: Graph, session_id: str) -> list[dict] | None:
    """Return full raw messages (with tool calls) saved from the last run, or None."""
    result = graph.query(
        "MATCH (s:Session {id: $id}) RETURN s.messages_raw",
        {"id": session_id},
    )
    if not result.result_set or not result.result_set[0][0]:
        return None
    return json.loads(result.result_set[0][0])


def update_session_raw_messages(graph: Graph, session_id: str, raw_messages: list[dict]) -> None:
    """Persist full raw messages (including tool calls) for session continuation."""
    graph.query(
        "MATCH (s:Session {id: $id}) SET s.messages_raw = $messages_raw",
        {"id": session_id, "messages_raw": json.dumps(raw_messages)},
    )


def update_session_messages(
    graph: Graph, session_id: str, messages: list[ChatMessage]
) -> None:
    """Overwrite the messages on an existing Session node."""
    messages_json = json.dumps([m.model_dump() for m in messages])
    graph.query(
        "MATCH (s:Session {id: $id}) SET s.messages = $messages",
        {"id": session_id, "messages": messages_json},
    )


def is_session_completed(graph: Graph, session_id: str) -> bool:
    """Check if a session has already been processed."""
    result = graph.query(
        "MATCH (s:Session {id: $id}) RETURN s.completed_at",
        {"id": session_id},
    )
    if not result.result_set:
        raise ValueError(f"Session '{session_id}' not found.")
    return result.result_set[0][0] is not None


class CompletedSessionRow(BaseModel):
    id: str
    summary: str
    graph_changes: dict
    completed_at: str


def get_sessions_since(graph: Graph, since_iso: str) -> list[CompletedSessionRow]:
    """Return sessions completed after the given ISO timestamp, for the theme agent."""
    result = graph.query(
        """
        MATCH (s:Session)
        WHERE s.completed_at IS NOT NULL AND s.completed_at > $since
        RETURN s.id, s.summary, s.graph_changes, s.completed_at
        ORDER BY s.completed_at ASC
        """,
        {"since": since_iso},
    )
    return [
        CompletedSessionRow(
            id=row[0],
            summary=row[1] or "",
            graph_changes=json.loads(row[2]) if row[2] else {},
            completed_at=row[3],
        )
        for row in result.result_set
    ]
