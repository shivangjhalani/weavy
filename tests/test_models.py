"""Tests for lifeos.memory.models Pydantic models."""
import pytest
from datetime import datetime, timezone


def test_node_creation_basic():
    """Node(id, type, summary) creates a valid node."""
    from lifeos.memory.models import Node
    node = Node(id="n1", type="person", summary="A test person")
    assert node.id == "n1"
    assert node.type == "person"
    assert node.summary == "A test person"


def test_node_type_is_free_string():
    """Node.type accepts any string — no enum constraint."""
    from lifeos.memory.models import Node
    # These would fail if type were an enum
    n1 = Node(id="n1", type="person", summary="test")
    n2 = Node(id="n2", type="recurring_theme", summary="test")
    n3 = Node(id="n3", type="project/goal", summary="test")
    n4 = Node(id="n4", type="ANYTHING_GOES", summary="test")
    assert n1.type == "person"
    assert n2.type == "recurring_theme"
    assert n3.type == "project/goal"
    assert n4.type == "ANYTHING_GOES"


def test_node_default_empty_aliases():
    """Node has empty aliases list by default."""
    from lifeos.memory.models import Node
    node = Node(id="n1", type="person", summary="test")
    assert node.aliases == []


def test_node_default_empty_log():
    """Node has empty log list by default."""
    from lifeos.memory.models import Node
    node = Node(id="n1", type="person", summary="test")
    assert node.log == []


def test_node_default_empty_refs():
    """Node has empty refs list by default."""
    from lifeos.memory.models import Node
    node = Node(id="n1", type="person", summary="test")
    assert node.refs == []


def test_node_default_none_embedding():
    """Node has None embedding by default."""
    from lifeos.memory.models import Node
    node = Node(id="n1", type="person", summary="test")
    assert node.embedding is None


def test_node_with_embedding():
    """Node accepts a list of floats as embedding."""
    from lifeos.memory.models import Node
    node = Node(id="n1", type="person", summary="test", embedding=[0.1, 0.2, 0.3])
    assert node.embedding == [0.1, 0.2, 0.3]


def test_edge_creation_basic():
    """Edge(id, type, source_id, target_id, summary) creates a valid edge."""
    from lifeos.memory.models import Edge
    edge = Edge(id="e1", type="knows", source_id="n1", target_id="n2", summary="n1 knows n2")
    assert edge.id == "e1"
    assert edge.type == "knows"
    assert edge.source_id == "n1"
    assert edge.target_id == "n2"
    assert edge.summary == "n1 knows n2"


def test_edge_type_is_free_string():
    """Edge.type accepts any string — no enum constraint."""
    from lifeos.memory.models import Edge
    e1 = Edge(id="e1", type="knows", source_id="n1", target_id="n2", summary="test")
    e2 = Edge(id="e2", type="aspires_toward", source_id="n1", target_id="n2", summary="test")
    assert e1.type == "knows"
    assert e2.type == "aspires_toward"


def test_edge_default_empty_log():
    """Edge has empty log list by default."""
    from lifeos.memory.models import Edge
    edge = Edge(id="e1", type="knows", source_id="n1", target_id="n2", summary="test")
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
        type="person",
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
