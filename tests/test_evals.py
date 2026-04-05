from unittest.mock import MagicMock, patch

from arakne.evals.runner import run_scenario
from arakne.evals.scenarios import EvalItem, load_dataset


def test_load_dataset_keeps_dataset_item_reference() -> None:
    dataset_item = MagicMock()
    dataset_item.id = "item-1"
    dataset_item.input = {"mode": "query", "question": "What changed?"}
    dataset_item.expected_output = {"answer": "A lot."}
    dataset_item.metadata = {"priority": "high"}
    dataset = MagicMock(items=[dataset_item])

    with patch("arakne.langfuse_client.get_langfuse") as mock_get_langfuse:
        mock_get_langfuse.return_value.get_dataset.return_value = dataset
        items = load_dataset("smoke-suite")

    assert len(items) == 1
    assert items[0].dataset_item is dataset_item
    assert items[0].metadata == {"priority": "high"}


def test_run_scenario_uses_loaded_dataset_item_link() -> None:
    dataset_item = MagicMock()
    eval_item = EvalItem(
        item_id="item-1",
        dataset_name="smoke-suite",
        mode="query",
        input={"question": "What changed?"},
        dataset_item=dataset_item,
    )
    trace = MagicMock(
        run_id="trace-1",
        status="completed",
        completion_payload={"answer": "A lot."},
        error=None,
    )

    with patch("arakne.evals.runner._run_eval_item", return_value=trace):
        result = run_scenario(eval_item, "smoke-run")

    dataset_item.link.assert_called_once_with(
        trace_or_observation=None,
        run_name="smoke-run",
        run_metadata={"mode": "query"},
        trace_id="trace-1",
    )
    assert result["trace_id"] == "trace-1"


def test_run_scenario_supports_theme_items() -> None:
    dataset_item = MagicMock()
    eval_item = EvalItem(
        item_id="item-2",
        dataset_name="smoke-suite",
        mode="theme",
        input={
            "summary": "Career direction changed.",
            "touched_nodes": [{"node_id": "node:1", "action": "updated"}],
        },
        dataset_item=dataset_item,
    )
    trace = MagicMock(
        run_id="trace-2",
        status="completed",
        completion_payload={"updated_themes": ["career-direction"]},
        error=None,
    )

    with patch("arakne.evals.runner._run_eval_item", return_value=trace) as mock_run_eval_item:
        result = run_scenario(eval_item, "smoke-run")

    mock_run_eval_item.assert_called_once_with(eval_item)
    dataset_item.link.assert_called_once_with(
        trace_or_observation=None,
        run_name="smoke-run",
        run_metadata={"mode": "theme"},
        trace_id="trace-2",
    )
    assert result["trace_id"] == "trace-2"
