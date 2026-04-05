"""
Eval scenarios — thin wrappers around Langfuse dataset items.

Datasets live in Langfuse. Use the Langfuse UI or API to create datasets and
add test items. This module provides helpers to fetch and run them.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class EvalItem(BaseModel):
    """A single eval test case, loaded from a Langfuse dataset item."""

    item_id: str
    dataset_name: str
    mode: Literal["ingestion", "query", "theme"]
    input: dict[str, Any]
    expected_output: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    dataset_item: Any | None = Field(default=None, exclude=True, repr=False)


def load_dataset(dataset_name: str) -> list[EvalItem]:
    """Fetch all items from a Langfuse dataset and return as EvalItem list."""
    from arakne.langfuse_client import get_langfuse

    dataset = get_langfuse().get_dataset(dataset_name)
    items: list[EvalItem] = []
    for item in dataset.items:
        input_payload = item.input or {}
        items.append(
            EvalItem(
                item_id=item.id,
                dataset_name=dataset_name,
                mode=input_payload.get("mode", "query"),
                input=input_payload,
                expected_output=item.expected_output,
                metadata=item.metadata or {},
                dataset_item=item,
            )
        )
    return items
