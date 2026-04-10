"""
Canonical source persistence — Session CRUD in FalkorDB.
"""

import json
from datetime import datetime

from falkordb import Graph
from pydantic import BaseModel

from weavy.models.canonical import Session, conversation_to_chat_messages
from weavy.models.tools import (
    GetSessionOutput,
    ListSessionsInput,
    ListSessionsOutput,
    SessionSummary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_session_props(graph: Graph, session_id: str) -> dict:
    result = graph.query(
        "MATCH (s:Session {id: $id}) RETURN s",
        {"id": session_id},
    )
    if not result.result_set:
        raise ValueError(f"Session '{session_id}' not found.")
    return result.result_set[0][0].properties


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


def create_session(graph: Graph, session: Session) -> None:
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
            "messages": json.dumps([m.model_dump() for m in session.messages]),
        },
    )


def get_session(
    graph: Graph, session_id: str, *, check_completed: bool = False
) -> Session:
    props = _get_session_props(graph, session_id)
    if check_completed and props.get("completed_at") is not None:
        raise ValueError(f"Session '{session_id}' is already completed.")
    raw: list[dict] = json.loads(props["messages"])
    return Session(
        id=props["id"],
        timestamp=datetime.fromisoformat(props["timestamp"]),
        messages=conversation_to_chat_messages(raw),
    )


def load_messages(graph: Graph, session_id: str) -> list[dict]:
    """Return the full raw message list for a session (used for agent continuation)."""
    props = _get_session_props(graph, session_id)
    return json.loads(props["messages"])


def update_messages(graph: Graph, session_id: str, messages: list[dict]) -> None:
    """Overwrite the messages on an existing Session node."""
    graph.query(
        "MATCH (s:Session {id: $id}) SET s.messages = $messages",
        {"id": session_id, "messages": json.dumps(messages)},
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
) -> GetSessionOutput:
    session = get_session(graph, session_id)
    return GetSessionOutput(
        session=Session(
            id=session.id,
            timestamp=session.timestamp,
            messages=session.messages[start_index:end_index],
        )
    )


# ---------------------------------------------------------------------------
# Session outcomes (written after agent processing)
# ---------------------------------------------------------------------------


def get_session_graph_changes(graph: Graph, session_id: str) -> dict:
    """Read existing graph_changes from a session, or {} if not yet set."""
    props = _get_session_props(graph, session_id)
    raw = props.get("graph_changes")
    result = json.loads(raw) if raw else {}
    return result if isinstance(result, dict) else {}


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


def is_session_completed(graph: Graph, session_id: str) -> bool:
    """Check if a session has already been processed."""
    return _get_session_props(graph, session_id).get("completed_at") is not None


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
