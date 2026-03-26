"""Tests for lifeos.memory.models Pydantic models."""
import pytest
from datetime import datetime, timezone


def test_node_creation_basic():
    """Node(id, name, summary) creates a valid node."""
    from lifeos.memory.models import Node
    node = Node(id="n1", name="Alice", summary="A test person")
    assert node.id == "n1"
    assert node.name == "Alice"
    assert node.summary == "A test person"


def test_node_name_is_free_string():
    """Node.name accepts any string — no enum constraint."""
    from lifeos.memory.models import Node
    # These would fail if name were an enum
    n1 = Node(id="n1", name="Alice", summary="test")
    n2 = Node(id="n2", name="recurring_theme/2024", summary="test")
    n3 = Node(id="n3", name="project/goal", summary="test")
    n4 = Node(id="n4", name="ANYTHING_GOES", summary="test")
    assert n1.name == "Alice"
    assert n2.name == "recurring_theme/2024"
    assert n3.name == "project/goal"
    assert n4.name == "ANYTHING_GOES"


def test_node_default_empty_aliases():
    """Node has empty aliases list by default."""
    from lifeos.memory.models import Node
    node = Node(id="n1", name="Alice", summary="test")
    assert node.aliases == []


def test_node_default_empty_log():
    """Node has empty log list by default."""
    from lifeos.memory.models import Node
    node = Node(id="n1", name="Alice", summary="test")
    assert node.log == []


def test_node_default_empty_refs():
    """Node has empty refs list by default."""
    from lifeos.memory.models import Node
    node = Node(id="n1", name="Alice", summary="test")
    assert node.refs == []


def test_node_default_none_embedding():
    """Node has None embedding by default."""
    from lifeos.memory.models import Node
    node = Node(id="n1", name="Alice", summary="test")
    assert node.embedding is None


def test_node_with_embedding():
    """Node accepts a list of floats as embedding."""
    from lifeos.memory.models import Node
    node = Node(id="n1", name="Alice", summary="test", embedding=[0.1, 0.2, 0.3])
    assert node.embedding == [0.1, 0.2, 0.3]


def test_edge_creation_basic():
    """Edge(id, label, source_id, target_id, summary) creates a valid edge."""
    from lifeos.memory.models import Edge
    edge = Edge(id="e1", label="knows", source_id="n1", target_id="n2", summary="n1 knows n2")
    assert edge.id == "e1"
    assert edge.label == "knows"
    assert edge.source_id == "n1"
    assert edge.target_id == "n2"
    assert edge.summary == "n1 knows n2"


def test_edge_label_is_free_string():
    """Edge.label accepts any string — no enum constraint."""
    from lifeos.memory.models import Edge
    e1 = Edge(id="e1", label="knows", source_id="n1", target_id="n2", summary="test")
    e2 = Edge(id="e2", label="aspires_toward", source_id="n1", target_id="n2", summary="test")
    assert e1.label == "knows"
    assert e2.label == "aspires_toward"


def test_edge_default_empty_log():
    """Edge has empty log list by default."""
    from lifeos.memory.models import Edge
    edge = Edge(id="e1", label="knows", source_id="n1", target_id="n2", summary="test")
    assert edge.log == []


def test_transcript_ref_creation():
    """TranscriptRef(transcript_id) creates valid ref with optional offsets."""
    from lifeos.memory.models import TranscriptRef
    ref = TranscriptRef(transcript_id="t1")
    assert ref.transcript_id == "t1"
    assert ref.start_offset is None
    assert ref.end_offset is None


def test_transcript_ref_with_offsets():
    """TranscriptRef accepts optional start_offset and end_offset."""
    from lifeos.memory.models import TranscriptRef
    ref = TranscriptRef(transcript_id="t1", start_offset=10, end_offset=50)
    assert ref.start_offset == 10
    assert ref.end_offset == 50


def test_log_entry_creation():
    """LogEntry(recorded_at, note) creates a valid entry."""
    from lifeos.memory.models import LogEntry
    now = datetime.now(timezone.utc)
    entry = LogEntry(recorded_at=now, note="Something happened")
    assert entry.recorded_at == now
    assert entry.note == "Something happened"


def test_node_with_aliases_and_log():
    """Node can be created with aliases and log entries."""
    from lifeos.memory.models import Node, LogEntry, TranscriptRef
    now = datetime.now(timezone.utc)
    node = Node(
        id="n1",
        name="Alice",
        summary="Alice from work",
        aliases=["Alice", "A"],
        log=[LogEntry(recorded_at=now, note="first mention")],
        refs=[TranscriptRef(transcript_id="t1", start_offset=5)],
    )
    assert node.aliases == ["Alice", "A"]
    assert len(node.log) == 1
    assert node.log[0].note == "first mention"
    assert len(node.refs) == 1
    assert node.refs[0].transcript_id == "t1"


def test_transcript_store_save_and_load(tmp_transcript_dir):
    """TranscriptStore.save() writes JSON; .load() reads it back correctly."""
    from lifeos.memory.store import TranscriptStore
    store = TranscriptStore(tmp_transcript_dir)
    data = {"text": "Hello world", "duration": 10.5}
    store.save("transcript-001", data)
    loaded = store.load("transcript-001")
    assert loaded is not None
    assert loaded["text"] == "Hello world"
    assert loaded["duration"] == 10.5


def test_transcript_store_load_nonexistent(tmp_transcript_dir):
    """TranscriptStore.load() returns None for nonexistent transcript."""
    from lifeos.memory.store import TranscriptStore
    store = TranscriptStore(tmp_transcript_dir)
    result = store.load("does-not-exist")
    assert result is None


def test_transcript_store_creates_dir(tmp_path):
    """TranscriptStore creates base_dir if it doesn't exist."""
    from lifeos.memory.store import TranscriptStore
    new_dir = tmp_path / "nested" / "transcripts"
    assert not new_dir.exists()
    store = TranscriptStore(new_dir)
    assert new_dir.exists()


def test_episode_span_creation():
    """EpisodeSpan(start_offset, end_offset, summary) creates a valid span with embedding=None."""
    from lifeos.memory.models import EpisodeSpan
    span = EpisodeSpan(start_offset=0, end_offset=100, summary="test topic")
    assert span.start_offset == 0
    assert span.end_offset == 100
    assert span.summary == "test topic"
    assert span.embedding is None


def test_transcript_creation():
    """Transcript(id, recorded_at, text) creates valid transcript with empty defaults."""
    from lifeos.memory.models import Transcript
    now = datetime.now(timezone.utc)
    t = Transcript(id="t1", recorded_at=now, text="Hello world")
    assert t.id == "t1"
    assert t.recorded_at == now
    assert t.text == "Hello world"
    assert t.segments == []
    assert t.episode_spans == []


def test_transcript_with_episode_spans():
    """Transcript with episode_spans round-trips correctly."""
    from lifeos.memory.models import Transcript, EpisodeSpan
    now = datetime.now(timezone.utc)
    span = EpisodeSpan(start_offset=0, end_offset=50, summary="intro section")
    t = Transcript(id="t2", recorded_at=now, text="Intro text here", episode_spans=[span])
    assert len(t.episode_spans) == 1
    assert t.episode_spans[0].summary == "intro section"
    assert t.episode_spans[0].start_offset == 0
    assert t.episode_spans[0].end_offset == 50
