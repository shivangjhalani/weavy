"""Unit tests for build_tools factory — all 13 agent tools with mocked graph."""
import uuid
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_store(transcript_data=None):
    """Create a mock TranscriptStore."""
    store = MagicMock()
    store.load.return_value = transcript_data or {"id": "t1", "text": "hello", "episode_spans": []}
    store.save.return_value = None
    return store


def make_graph():
    """Create a mock graph object (passed to build_tools)."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Test: build_tools returns correct counts
# ---------------------------------------------------------------------------

def test_build_tools_returns_13_tools():
    """build_tools returns a dict with exactly 13 tool callables."""
    from lifeos.agent.tools import build_tools

    graph = make_graph()
    store = make_store()
    tools_dict, declarations = build_tools(graph, store)
    assert len(tools_dict) == 13, f"Expected 13 tools, got {len(tools_dict)}: {list(tools_dict.keys())}"


def test_build_tools_returns_13_declarations():
    """build_tools returns a list with exactly 13 FunctionDeclaration objects."""
    from lifeos.agent.tools import build_tools

    graph = make_graph()
    store = make_store()
    tools_dict, declarations = build_tools(graph, store)
    assert len(declarations) == 13, f"Expected 13 declarations, got {len(declarations)}"


def test_build_tools_tool_names():
    """build_tools returns all 13 expected tool names."""
    from lifeos.agent.tools import build_tools

    graph = make_graph()
    store = make_store()
    tools_dict, _ = build_tools(graph, store)
    expected = {
        "search_nodes_by_alias",
        "search_nodes_by_embedding",
        "get_node",
        "search_edges_by_embedding",
        "create_node",
        "update_node",
        "delete_node",
        "get_node_edges",
        "create_edge",
        "update_edge",
        "delete_edge",
        "get_edge",
        "create_episode_spans",
    }
    assert set(tools_dict.keys()) == expected


# ---------------------------------------------------------------------------
# Test: search_nodes_by_alias
# ---------------------------------------------------------------------------

def test_search_nodes_by_alias_calls_graph():
    """search_nodes_by_alias calls graph_module.search_nodes_by_alias and returns correct structure."""
    from lifeos.agent.tools import build_tools
    import lifeos.memory.graph as graph_module

    fake_results = [{"id": "n1", "name": "Alice", "aliases": ["Alice"], "summary": "A friend"}]
    with patch.object(graph_module, "search_nodes_by_alias", return_value=fake_results) as mock_fn:
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        result = tools_dict["search_nodes_by_alias"](alias="Alice")

    mock_fn.assert_called_once()
    assert result["count"] == 1
    assert result["matches"] == fake_results


# ---------------------------------------------------------------------------
# Test: search_nodes_by_embedding
# ---------------------------------------------------------------------------

def test_search_nodes_by_embedding_enriched():
    """search_nodes_by_embedding returns name and aliases in each match (D-01)."""
    from lifeos.agent.tools import build_tools
    import lifeos.memory.graph as graph_module

    fake_results = [
        ("n1", "Alice", ["Alice", "ali"], "A friend", 0.92),
        ("n2", "Bob", ["Bob"], "Another person", 0.78),
    ]
    with patch.object(graph_module, "vector_search", return_value=fake_results) as mock_fn:
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        result = tools_dict["search_nodes_by_embedding"](query="fear of change", k=3)

    mock_fn.assert_called_once()
    matches = result["matches"]
    assert len(matches) == 2
    assert matches[0]["node_id"] == "n1"
    assert matches[0]["name"] == "Alice"
    assert matches[0]["aliases"] == ["Alice", "ali"]
    assert matches[0]["summary"] == "A friend"
    assert matches[0]["score"] == 0.92


# ---------------------------------------------------------------------------
# Test: create_node
# ---------------------------------------------------------------------------

def test_create_node_generates_uuid():
    """create_node returns a dict with node_id that is a valid UUID."""
    from lifeos.agent.tools import build_tools
    import lifeos.memory.graph as graph_module

    with patch.object(graph_module, "create_node", return_value=None):
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        result = tools_dict["create_node"](name="Alice", summary="A close friend")

    assert "node_id" in result
    assert result["created"] is True
    # Verify it's a valid UUID
    parsed = uuid.UUID(result["node_id"])
    assert str(parsed) == result["node_id"]


def test_create_node_calls_graph_create():
    """create_node calls graph_module.create_node with a Node object."""
    from lifeos.agent.tools import build_tools
    from lifeos.memory.models import Node
    import lifeos.memory.graph as graph_module

    with patch.object(graph_module, "create_node", return_value=None) as mock_fn:
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        tools_dict["create_node"](name="Bob", summary="A colleague")

    mock_fn.assert_called_once()
    call_args = mock_fn.call_args
    # Second arg is the Node object
    node_arg = call_args[0][1]
    assert isinstance(node_arg, Node)
    assert node_arg.name == "Bob"
    assert node_arg.summary == "A colleague"


def test_create_node_default_aliases():
    """create_node defaults aliases to [name] when not provided."""
    from lifeos.agent.tools import build_tools
    import lifeos.memory.graph as graph_module

    with patch.object(graph_module, "create_node", return_value=None) as mock_fn:
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        tools_dict["create_node"](name="Carol", summary="A neighbor")

    node_arg = mock_fn.call_args[0][1]
    assert "Carol" in node_arg.aliases


# ---------------------------------------------------------------------------
# Test: update_node
# ---------------------------------------------------------------------------

def test_update_node_passes_aliases():
    """update_node passes new_aliases through to graph_module.update_node."""
    from lifeos.agent.tools import build_tools
    import lifeos.memory.graph as graph_module

    with patch.object(graph_module, "update_node", return_value=None) as mock_fn:
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        result = tools_dict["update_node"](
            node_id="n-123",
            summary="Updated summary",
            log_note="Changed something",
            new_aliases=["Ali", "Alicia"],
        )

    mock_fn.assert_called_once()
    call_kwargs = mock_fn.call_args[1]
    assert call_kwargs["new_aliases"] == ["Ali", "Alicia"]
    assert result["node_id"] == "n-123"
    assert result["updated"] is True


# ---------------------------------------------------------------------------
# Test: delete_node
# ---------------------------------------------------------------------------

def test_delete_node_calls_graph():
    """delete_node calls graph_module.delete_node with the correct node_id."""
    from lifeos.agent.tools import build_tools
    import lifeos.memory.graph as graph_module

    with patch.object(graph_module, "delete_node", return_value=None) as mock_fn:
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        result = tools_dict["delete_node"](node_id="n-456")

    mock_fn.assert_called_once_with(graph, "n-456")
    assert result["node_id"] == "n-456"
    assert result["deleted"] is True


# ---------------------------------------------------------------------------
# Test: create_edge
# ---------------------------------------------------------------------------

def test_create_edge_generates_uuid():
    """create_edge returns a dict with edge_id that is a valid UUID."""
    from lifeos.agent.tools import build_tools
    import lifeos.memory.graph as graph_module

    with patch.object(graph_module, "create_edge", return_value=None):
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        result = tools_dict["create_edge"](
            source_id="n1",
            target_id="n2",
            label="fears",
            summary="n1 is afraid of n2",
        )

    assert "edge_id" in result
    assert result["created"] is True
    parsed = uuid.UUID(result["edge_id"])
    assert str(parsed) == result["edge_id"]


def test_create_edge_calls_graph_create():
    """create_edge calls graph_module.create_edge with an Edge object."""
    from lifeos.agent.tools import build_tools
    from lifeos.memory.models import Edge
    import lifeos.memory.graph as graph_module

    with patch.object(graph_module, "create_edge", return_value=None) as mock_fn:
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        tools_dict["create_edge"](
            source_id="n1",
            target_id="n2",
            label="knows",
            summary="n1 knows n2",
        )

    mock_fn.assert_called_once()
    edge_arg = mock_fn.call_args[0][1]
    assert isinstance(edge_arg, Edge)
    assert edge_arg.label == "knows"
    assert edge_arg.source_id == "n1"
    assert edge_arg.target_id == "n2"


# ---------------------------------------------------------------------------
# Test: update_edge
# ---------------------------------------------------------------------------

def test_update_edge_calls_graph():
    """update_edge calls graph_module.update_edge with correct params."""
    from lifeos.agent.tools import build_tools
    import lifeos.memory.graph as graph_module

    with patch.object(graph_module, "update_edge", return_value=None) as mock_fn:
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        result = tools_dict["update_edge"](
            edge_id="e-789",
            summary="Updated relationship",
            log_note="Relationship evolved",
        )

    mock_fn.assert_called_once()
    assert result["edge_id"] == "e-789"
    assert result["updated"] is True


# ---------------------------------------------------------------------------
# Test: delete_edge
# ---------------------------------------------------------------------------

def test_delete_edge_calls_graph():
    """delete_edge calls graph_module.delete_edge with the correct edge_id."""
    from lifeos.agent.tools import build_tools
    import lifeos.memory.graph as graph_module

    with patch.object(graph_module, "delete_edge", return_value=None) as mock_fn:
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        result = tools_dict["delete_edge"](edge_id="e-abc")

    mock_fn.assert_called_once_with(graph, "e-abc")
    assert result["edge_id"] == "e-abc"
    assert result["deleted"] is True


# ---------------------------------------------------------------------------
# Test: create_episode_spans
# ---------------------------------------------------------------------------

def test_create_episode_spans_embeds_summaries():
    """create_episode_spans generates embeddings for each span summary."""
    from lifeos.agent.tools import build_tools

    fake_embedding = [0.1, 0.2, 0.3]
    transcript_data = {"id": "t1", "text": "Full transcript text", "episode_spans": []}

    store = make_store(transcript_data)
    graph = make_graph()

    # Patch embed_text in the tools module where it is imported
    with patch("lifeos.agent.tools.embed_text", return_value=fake_embedding) as mock_embed:
        tools_dict, _ = build_tools(graph, store)
        spans = [
            {"start_offset": 0, "end_offset": 100, "summary": "Introduction segment"},
            {"start_offset": 100, "end_offset": 200, "summary": "Main topic"},
        ]
        result = tools_dict["create_episode_spans"](transcript_id="t1", spans=spans)

    assert mock_embed.call_count == 2
    assert result["transcript_id"] == "t1"
    assert result["spans_created"] == 2
    # Verify store.save was called
    store.save.assert_called_once()


def test_create_episode_spans_appends_to_existing():
    """create_episode_spans appends new spans to any existing episode_spans."""
    from lifeos.agent.tools import build_tools

    existing_span = {"start_offset": 0, "end_offset": 50, "summary": "old", "embedding": [0.1]}
    transcript_data = {"id": "t1", "text": "...", "episode_spans": [existing_span]}

    store = make_store(transcript_data)
    graph = make_graph()

    with patch("lifeos.agent.tools.embed_text", return_value=[0.5]):
        tools_dict, _ = build_tools(graph, store)
        tools_dict["create_episode_spans"](
            transcript_id="t1",
            spans=[{"start_offset": 50, "end_offset": 100, "summary": "new span"}],
        )

    saved_data = store.save.call_args[0][1]
    assert len(saved_data["episode_spans"]) == 2


# ---------------------------------------------------------------------------
# Test: FunctionDeclaration names match tool dict keys
# ---------------------------------------------------------------------------

def test_declaration_names_match_tool_keys():
    """Every FunctionDeclaration name matches a key in the tools dict."""
    from lifeos.agent.tools import build_tools

    graph = make_graph()
    store = make_store()
    tools_dict, declarations = build_tools(graph, store)
    decl_names = {d["function"]["name"] for d in declarations}
    assert decl_names == set(tools_dict.keys())


# ---------------------------------------------------------------------------
# Test: get_node tool
# ---------------------------------------------------------------------------

def test_get_node_tool_strips_embedding_and_parses_log():
    """get_node tool returns name/aliases/summary/log/refs, excludes embedding."""
    from lifeos.agent.tools import build_tools
    import lifeos.memory.graph as graph_module

    raw_node = {
        "name": "Alice",
        "aliases": ["Alice", "ali"],
        "summary": "A close friend",
        "log": '[{"recorded_at": "2026-01-01T00:00:00+00:00", "note": "First mention"}]',
        "refs": '[{"transcript_id": "t1", "start_offset": 0, "end_offset": 100}]',
        "embedding": [0.1, 0.2, 0.3],  # should be stripped
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    with patch.object(graph_module, "get_node", return_value=raw_node):
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        result = tools_dict["get_node"](node_id="n1")

    assert result["name"] == "Alice"
    assert result["aliases"] == ["Alice", "ali"]
    assert isinstance(result["log"], list), "log must be parsed list"
    assert result["log"][0]["note"] == "First mention"
    assert isinstance(result["refs"], list), "refs must be parsed list"
    assert result["refs"][0]["transcript_id"] == "t1"
    assert "embedding" not in result, "embedding must be excluded from tool response"


def test_get_node_tool_not_found():
    """get_node tool returns error dict when node does not exist."""
    from lifeos.agent.tools import build_tools
    import lifeos.memory.graph as graph_module

    with patch.object(graph_module, "get_node", return_value=None):
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        result = tools_dict["get_node"](node_id="nonexistent")

    assert result == {"error": "not found"}


# ---------------------------------------------------------------------------
# Test: get_node_edges tool
# ---------------------------------------------------------------------------

def test_get_node_edges_tool_returns_correct_shape():
    """get_node_edges tool wraps graph_module.get_node_edges and returns count."""
    from lifeos.agent.tools import build_tools
    import lifeos.memory.graph as graph_module

    fake_edges = [
        {
            "edge_id": "e1",
            "label": "fears",
            "summary": "fears X",
            "source": {"id": "n1", "name": "Alice"},
            "target": {"id": "n2", "name": "Fear"},
            "direction": "outgoing",
        }
    ]
    with patch.object(graph_module, "get_node_edges", return_value=fake_edges) as mock_fn:
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        result = tools_dict["get_node_edges"](node_id="n1")

    mock_fn.assert_called_once()
    assert result["node_id"] == "n1"
    assert result["count"] == 1
    assert result["edges"][0]["direction"] == "outgoing"
    assert result["edges"][0]["label"] == "fears"


# ---------------------------------------------------------------------------
# Test: get_edge tool
# ---------------------------------------------------------------------------

def test_get_edge_tool_returns_edge_state():
    """get_edge tool wraps graph_module.get_edge and returns full state."""
    from lifeos.agent.tools import build_tools
    import lifeos.memory.graph as graph_module

    fake_edge = {
        "edge_id": "e1",
        "label": "fears",
        "summary": "fears X",
        "source_id": "n1",
        "target_id": "n2",
        "log": [{"recorded_at": "2026-01-01T00:00:00+00:00", "note": "Created"}],
        "refs": [],
        "created_at": "2026-01-01",
        "updated_at": "2026-01-01",
    }
    with patch.object(graph_module, "get_edge", return_value=fake_edge) as mock_fn:
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        result = tools_dict["get_edge"](edge_id="e1")

    mock_fn.assert_called_once()
    assert result["edge_id"] == "e1"
    assert result["label"] == "fears"
    assert isinstance(result["log"], list)


def test_get_edge_tool_not_found():
    """get_edge tool returns error dict when edge does not exist."""
    from lifeos.agent.tools import build_tools
    import lifeos.memory.graph as graph_module

    with patch.object(graph_module, "get_edge", return_value=None):
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        result = tools_dict["get_edge"](edge_id="nonexistent")

    assert result == {"error": "not found"}


# ---------------------------------------------------------------------------
# Test: search_edges_by_embedding tool
# ---------------------------------------------------------------------------

def test_search_edges_by_embedding_tool_returns_matches():
    """search_edges_by_embedding delegates to graph_module.vector_search_edges."""
    from lifeos.agent.tools import build_tools
    import lifeos.memory.graph as graph_module

    fake_results = [("e1", "fears change", 0.88), ("e2", "resists growth", 0.74)]
    with patch.object(graph_module, "vector_search_edges", return_value=fake_results) as mock_fn:
        graph = make_graph()
        store = make_store()
        tools_dict, _ = build_tools(graph, store)
        result = tools_dict["search_edges_by_embedding"](query="avoiding change", k=5)

    mock_fn.assert_called_once()
    matches = result["matches"]
    assert len(matches) == 2
    assert matches[0]["edge_id"] == "e1"
    assert matches[0]["summary"] == "fears change"
    assert matches[0]["score"] == 0.88
