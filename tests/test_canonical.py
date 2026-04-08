"""
Phase 2 tests — Transcript and ChatSession CRUD.
Requires a running FalkorDB instance (provided by devenv up).
Uses the "weavy_test" graph to avoid touching the main graph.
"""

import json
from datetime import datetime, timezone

import pytest
from falkordb import Graph

from weavy.models.canonical import (
    ChatMessage,
    ChatSession,
    Transcript,
    TranscriptSegment,
)
from weavy.models.tools import ListChatsInput, ListTranscriptsInput
from weavy.store.canonical import (
    create_chat_session,
    create_transcript,
    get_chat,
    get_chat_session,
    get_transcript,
    get_transcript_span,
    list_chats,
    list_transcripts,
)
from weavy.store.client import get_graph
from weavy.store.system import increment_counter, init_system

TEST_GRAPH = "weavy_test"

TRANSCRIPT_SEGMENTS = [
    TranscriptSegment(
        start=0.0,
        end=14.0,
        text="So I've been thinking about this career decision a lot lately.",
    ),
    TranscriptSegment(
        start=14.0,
        end=28.0,
        text="I know I should probably just quit but the mortgage keeps stopping me.",
    ),
    TranscriptSegment(
        start=28.0,
        end=40.0,
        text="And honestly I think I'm scared of what happens if I actually do it.",
    ),
]


@pytest.fixture
def graph() -> Graph:
    g = get_graph(TEST_GRAPH)
    g.query("MATCH (s:System) DELETE s")
    g.query("MATCH (t:Transcript) DELETE t")
    g.query("MATCH (c:ChatSession) DELETE c")
    init_system(g)
    yield g
    g.query("MATCH (s:System) DELETE s")
    g.query("MATCH (t:Transcript) DELETE t")
    g.query("MATCH (c:ChatSession) DELETE c")


def _make_transcript(
    graph: Graph, segments: list[TranscriptSegment] = TRANSCRIPT_SEGMENTS
) -> Transcript:
    rec_id = increment_counter(graph, "rec")
    t = Transcript(
        id=rec_id,
        audio_path=f"/audio/{rec_id}.m4a",
        timestamp=datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        segments=segments,
    )
    create_transcript(graph, t)
    return t


def _make_chat(graph: Graph, messages: list[ChatMessage] | None = None) -> ChatSession:
    if messages is None:
        messages = [
            ChatMessage(role="user", content="Hello"),
            ChatMessage(role="assistant", content="Hi there"),
            ChatMessage(role="user", content="How are you?"),
        ]
    chat_id = increment_counter(graph, "chat")
    s = ChatSession(
        id=chat_id,
        timestamp=datetime(2024, 6, 2, 10, 0, 0, tzinfo=timezone.utc),
        messages=messages,
    )
    create_chat_session(graph, s)
    return s


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------


def test_create_and_get_transcript(graph: Graph) -> None:
    t = _make_transcript(graph)
    fetched = get_transcript(graph, t.id)

    assert fetched.id == t.id
    assert fetched.audio_path == t.audio_path
    assert fetched.timestamp == t.timestamp
    assert fetched.segments == t.segments
    assert "[0:00]" in fetched.text
    assert "[0:14]" in fetched.text


def test_get_transcript_not_found(graph: Graph) -> None:
    with pytest.raises(ValueError, match="not found"):
        get_transcript(graph, "rec:999")


def test_list_transcripts_no_filter(graph: Graph) -> None:
    t1 = _make_transcript(graph)
    t2 = _make_transcript(graph)
    output = list_transcripts(graph, ListTranscriptsInput())

    ids = [t.id for t in output.transcripts]
    assert t1.id in ids
    assert t2.id in ids


def test_list_transcripts_date_range(graph: Graph) -> None:
    t = _make_transcript(graph)
    # Range that covers the transcript
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 31, tzinfo=timezone.utc)
    output = list_transcripts(graph, ListTranscriptsInput(date_range=[start, end]))
    assert any(ts.id == t.id for ts in output.transcripts)

    # Range that excludes the transcript
    past_start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    past_end = datetime(2023, 12, 31, tzinfo=timezone.utc)
    output_empty = list_transcripts(
        graph, ListTranscriptsInput(date_range=[past_start, past_end])
    )
    assert all(ts.id != t.id for ts in output_empty.transcripts)


def test_list_transcripts_limit(graph: Graph) -> None:
    for _ in range(3):
        _make_transcript(graph)
    output = list_transcripts(graph, ListTranscriptsInput(limit=2))
    assert len(output.transcripts) <= 2


def test_list_transcripts_json_humanizes_timestamp(graph: Graph) -> None:
    _make_transcript(graph)
    output = list_transcripts(graph, ListTranscriptsInput(limit=1))

    payload = json.loads(output.model_dump_json())
    assert "UTC" in payload["transcripts"][0]["timestamp"]
    assert "2024" in payload["transcripts"][0]["timestamp"]


def test_get_transcript_span_exact(graph: Graph) -> None:
    t = _make_transcript(graph)
    result = get_transcript_span(graph, t.id, start_offset=14, end_offset=27)

    assert "mortgage" in result.text
    assert "career decision" not in result.text
    assert "scared" not in result.text
    assert result.transcript_id == t.id


def test_get_transcript_span_full_range(graph: Graph) -> None:
    t = _make_transcript(graph)
    result = get_transcript_span(graph, t.id, start_offset=0, end_offset=3600)

    assert "career decision" in result.text
    assert "mortgage" in result.text
    assert "scared" in result.text


def test_get_transcript_span_with_context(graph: Graph) -> None:
    t = _make_transcript(graph)
    # Request only the middle segment, but add 15s of context on each side
    result = get_transcript_span(
        graph, t.id, start_offset=14, end_offset=27, context_secs=15
    )

    assert "career decision" in result.text  # segment before, pulled in by context
    assert "mortgage" in result.text
    assert "scared" in result.text  # segment after, pulled in by context


# ---------------------------------------------------------------------------
# ChatSession
# ---------------------------------------------------------------------------


def test_create_and_get_chat_session(graph: Graph) -> None:
    s = _make_chat(graph)
    fetched = get_chat_session(graph, s.id)

    assert fetched.id == s.id
    assert fetched.timestamp == s.timestamp
    assert len(fetched.messages) == len(s.messages)
    assert fetched.messages[0].role == "user"
    assert fetched.messages[0].content == "Hello"
    assert fetched.messages[1].role == "assistant"


def test_get_chat_session_not_found(graph: Graph) -> None:
    with pytest.raises(ValueError, match="not found"):
        get_chat_session(graph, "chat:999")


def test_list_chats(graph: Graph) -> None:
    s1 = _make_chat(graph)
    s2 = _make_chat(graph)
    output = list_chats(graph, ListChatsInput())

    ids = [c.id for c in output.chats]
    assert s1.id in ids
    assert s2.id in ids


def test_list_chats_json_humanizes_timestamp(graph: Graph) -> None:
    _make_chat(graph)
    output = list_chats(graph, ListChatsInput(limit=1))

    payload = json.loads(output.model_dump_json())
    assert "UTC" in payload["chats"][0]["timestamp"]
    assert "2024" in payload["chats"][0]["timestamp"]


def test_get_chat_full(graph: Graph) -> None:
    s = _make_chat(graph)
    result = get_chat(graph, s.id, None, None)

    assert len(result.session.messages) == 3
    assert result.session.messages[2].content == "How are you?"


def test_get_chat_json_humanizes_timestamp(graph: Graph) -> None:
    s = _make_chat(graph)
    result = get_chat(graph, s.id, None, None)

    payload = json.loads(result.model_dump_json())
    assert "UTC" in payload["session"]["timestamp"]
    assert "2024" in payload["session"]["timestamp"]


def test_get_chat_with_start_index(graph: Graph) -> None:
    s = _make_chat(graph)
    result = get_chat(graph, s.id, 1, None)

    assert len(result.session.messages) == 2
    assert result.session.messages[0].role == "assistant"


def test_get_chat_with_end_index(graph: Graph) -> None:
    s = _make_chat(graph)
    result = get_chat(graph, s.id, None, 2)

    assert len(result.session.messages) == 2
    assert result.session.messages[-1].role == "assistant"


def test_get_chat_with_slice(graph: Graph) -> None:
    s = _make_chat(graph)
    result = get_chat(graph, s.id, 1, 2)

    assert len(result.session.messages) == 1
    assert result.session.messages[0].role == "assistant"
    assert result.session.messages[0].content == "Hi there"
