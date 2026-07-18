"""Episode chunking/search and the create_node duplicate guard."""

import pytest

from tests.helpers import reset_test_graph
from weavy.application.session_runs import create_session
from weavy.harness.tracing import new_trace
from weavy.models.graph import ProvenanceInput
from weavy.models.traces import RunTrace
from weavy.services import memory


@pytest.fixture
def graph():
    yield reset_test_graph("Session", "Chunk")


def _trace() -> RunTrace:
    return new_trace("ingestion", "")


def _provenance() -> ProvenanceInput:
    return ProvenanceInput(source_id="s:1")


# --- chunk_text -----------------------------------------------------------


def test_chunk_text_packs_lines_with_overlap():
    lines = [f"speaker: line {i} " + "x" * 60 for i in range(20)]
    chunks = memory.chunk_text("\n".join(lines), target=300)
    assert len(chunks) > 1
    # consecutive chunks share one line of overlap
    for a, b in zip(chunks, chunks[1:]):
        assert a.splitlines()[-1] == b.splitlines()[0]
    # every line survives somewhere
    joined = "\n".join(chunks)
    assert all(line in joined for line in lines)


def test_chunk_text_empty_and_blank():
    assert memory.chunk_text("") == []
    assert memory.chunk_text("\n  \n") == []


def test_chunk_text_hard_splits_long_line():
    chunks = memory.chunk_text("y" * 1000, target=300)
    assert all(len(c) <= 300 for c in chunks)


# --- episode indexing + search -------------------------------------------


def test_session_with_text_indexes_chunks_and_search_finds_episode(graph):
    session_id = create_session("Ada: I adopted a guinea pig named Oscar.", graph)
    rows = graph.query(
        "MATCH (s:Session {id: $id})-[:HAS_CHUNK]->(c:Chunk) RETURN c.text",
        {"id": session_id},
    ).result_set
    assert rows, "episode text should be chunk-indexed"

    out = memory.search_graph(graph, query="guinea pig named Oscar")
    episode_hits = [r for r in out.results if r.kind == "episode"]
    assert episode_hits and episode_hits[0].id == session_id
    assert "Oscar" in episode_hits[0].text


def test_query_session_without_text_indexes_nothing(graph):
    session_id = create_session("", graph)
    rows = graph.query(
        "MATCH (s:Session {id: $id})-[:HAS_CHUNK]->(c:Chunk) RETURN c",
        {"id": session_id},
    ).result_set
    assert rows == []


# --- create_node duplicate guard ------------------------------------------


def test_create_node_refuses_alias_duplicate(graph):
    first = memory.create_node(
        graph,
        aliases=["Melanie"],
        summary="Melanie is a potter.",
        note="n",
        provenance=_provenance(),
        trace=_trace(),
    )
    assert first.ok

    dup = memory.create_node(
        graph,
        aliases=["melanie"],
        summary="A supportive parent who paints.",
        note="n",
        provenance=_provenance(),
        trace=_trace(),
    )
    assert not dup.ok
    assert first.id in (dup.message or "")


def test_create_node_force_overrides_guard(graph):
    memory.create_node(
        graph,
        aliases=["Alex"],
        summary="Alex the engineer.",
        note="n",
        provenance=_provenance(),
        trace=_trace(),
    )
    forced = memory.create_node(
        graph,
        aliases=["Alex"],
        summary="A different Alex — a chef.",
        note="n",
        provenance=_provenance(),
        trace=_trace(),
        force=True,
    )
    assert forced.ok


def test_create_node_allows_distinct_entities(graph):
    a = memory.create_node(
        graph,
        aliases=["Oscar"],
        summary="A guinea pig.",
        note="n",
        provenance=_provenance(),
        trace=_trace(),
    )
    b = memory.create_node(
        graph,
        aliases=["Pottery class"],
        summary="A weekly pottery class.",
        note="n",
        provenance=_provenance(),
        trace=_trace(),
    )
    assert a.ok and b.ok
