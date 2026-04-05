"""
Completion tools — termination signals for each agent mode.
"""

from weavy.models.tools import (
    CompleteIngestionInput,
    CompleteThemeUpdateInput,
    DeliverResponseInput,
    OperationResult,
)
from weavy.models.traces import RunTrace, graph_delta


def complete_ingestion(params: CompleteIngestionInput, trace: RunTrace) -> OperationResult:
    trace.completion_payload = {
        **params.model_dump(),
        **graph_delta(trace.touched_nodes, trace.touched_edges),
    }
    return OperationResult(ok=True)


def deliver_response(params: DeliverResponseInput, trace: RunTrace) -> OperationResult:
    trace.completion_payload = params.model_dump()
    return OperationResult(ok=True)


def complete_theme_update(
    params: CompleteThemeUpdateInput, trace: RunTrace
) -> OperationResult:
    trace.completion_payload = params.model_dump()
    return OperationResult(ok=True)
