"""Tests for log compression module — per COMP-01, COMP-02, COMP-03."""

import json
from unittest.mock import MagicMock, patch

from lifeos.agent.compress import (
    compress_log,
    count_tokens,
    needs_compression,
    run_compression_pass,
)

TEST_MODEL = "gemini/gemini-2.5-flash"


def _make_litellm_response(content: dict) -> MagicMock:
    """Build a mock litellm completion response with the given content dict."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(content)
    return mock_response


def test_count_tokens_returns_int():
    """count_tokens returns a positive integer for any string."""
    result = count_tokens("hello world")
    assert isinstance(result, int)
    assert result > 0


def test_needs_compression_under_threshold():
    """needs_compression returns False for a short log JSON string."""
    short_log = json.dumps([{"recorded_at": "2024-01-01T00:00:00Z", "note": "short note"}])
    assert needs_compression(short_log) is False


def test_needs_compression_over_threshold():
    """needs_compression returns True when log JSON exceeds 2000 tokens."""
    # Generate a log with enough text to exceed 2000 cl100k_base tokens
    long_note = "This is a very detailed log entry that goes on and on. " * 50
    big_log = json.dumps([
        {"recorded_at": f"2024-01-{i:02d}T00:00:00Z", "note": long_note}
        for i in range(1, 20)
    ])
    assert needs_compression(big_log) is True


def test_compress_log_short_list_unchanged():
    """compress_log returns entries unchanged when list has <= 3 entries."""
    entries = [
        {"recorded_at": "2024-01-01T00:00:00Z", "note": "first"},
        {"recorded_at": "2024-01-02T00:00:00Z", "note": "second"},
    ]
    with patch("litellm.completion") as mock_completion:
        result = compress_log(entries, TEST_MODEL)
    assert result == entries
    # litellm should NOT be called for short lists
    mock_completion.assert_not_called()


def test_compress_log_splits_correctly():
    """compress_log with 5 entries keeps last 3, compresses first 2 via litellm."""
    entries = [
        {"recorded_at": "2024-01-01T00:00:00Z", "note": "entry1"},
        {"recorded_at": "2024-01-02T00:00:00Z", "note": "entry2"},
        {"recorded_at": "2024-01-03T00:00:00Z", "note": "entry3"},
        {"recorded_at": "2024-01-04T00:00:00Z", "note": "entry4"},
        {"recorded_at": "2024-01-05T00:00:00Z", "note": "entry5"},
    ]

    compressed_entry = {"recorded_at": "2024-01-01T00:00:00Z", "note": "compressed"}
    mock_response = _make_litellm_response(compressed_entry)

    with patch("litellm.completion", return_value=mock_response):
        result = compress_log(entries, TEST_MODEL)

    # Should be: [compressed_entry, entry3, entry4, entry5]
    assert len(result) == 4
    assert result[0] == compressed_entry
    assert result[1] == entries[2]
    assert result[2] == entries[3]
    assert result[3] == entries[4]


def test_compress_log_sends_only_older_to_litellm():
    """compress_log sends only the first 2 entries (not last 3) to litellm."""
    entries = [
        {"recorded_at": "2024-01-01T00:00:00Z", "note": "old1"},
        {"recorded_at": "2024-01-02T00:00:00Z", "note": "old2"},
        {"recorded_at": "2024-01-03T00:00:00Z", "note": "recent1"},
        {"recorded_at": "2024-01-04T00:00:00Z", "note": "recent2"},
        {"recorded_at": "2024-01-05T00:00:00Z", "note": "recent3"},
    ]

    compressed_entry = {"recorded_at": "2024-01-01T00:00:00Z", "note": "compressed"}
    mock_response = _make_litellm_response(compressed_entry)

    with patch("litellm.completion", return_value=mock_response) as mock_completion:
        compress_log(entries, TEST_MODEL)

    # Verify litellm.completion was called once
    mock_completion.assert_called_once()
    call_kwargs = mock_completion.call_args

    # The user message content should include only the older entries (old1, old2)
    messages = call_kwargs.kwargs.get("messages", [])
    user_content = next((m["content"] for m in messages if m["role"] == "user"), "")
    assert "old1" in user_content
    assert "old2" in user_content
    assert "recent1" not in user_content
    assert "recent3" not in user_content


def test_run_compression_pass_no_overbudget():
    """run_compression_pass returns 0 when no logs exceed the threshold."""
    short_log = json.dumps([{"recorded_at": "2024-01-01T00:00:00Z", "note": "short"}])

    mock_graph = MagicMock()

    with patch("lifeos.agent.compress.graph_module") as mock_graph_module:
        with patch("litellm.completion") as mock_completion:
            mock_graph_module.get_node.return_value = {"log": short_log}
            result = run_compression_pass(
                mock_graph,
                modified_node_ids=["node-1"],
                modified_edge_ids=[],
                model=TEST_MODEL,
            )
    assert result == 0
    mock_completion.assert_not_called()


def test_run_compression_pass_compresses_node():
    """run_compression_pass compresses an over-budget node log and calls set_node_log."""
    long_note = "This is a detailed entry covering many complex topics. " * 50
    over_budget_log = json.dumps([
        {"recorded_at": f"2024-01-{i:02d}T00:00:00Z", "note": long_note}
        for i in range(1, 20)
    ])

    mock_graph = MagicMock()

    compressed_entry = {"recorded_at": "2024-01-01T00:00:00Z", "note": "compressed history"}
    mock_response = _make_litellm_response(compressed_entry)

    with patch("lifeos.agent.compress.graph_module") as mock_graph_module:
        with patch("litellm.completion", return_value=mock_response):
            mock_graph_module.get_node.return_value = {"log": over_budget_log}
            result = run_compression_pass(
                mock_graph,
                modified_node_ids=["node-1"],
                modified_edge_ids=[],
                model=TEST_MODEL,
            )
            # set_node_log must be called (not update_node)
            mock_graph_module.set_node_log.assert_called_once()
            mock_graph_module.update_node.assert_not_called()

    assert result == 1
