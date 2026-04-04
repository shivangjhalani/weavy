"""
Completion tools — termination signals for each agent mode.
"""

from arakne.models.tools import (
    CompleteIngestionInput,
    CompleteThemeUpdateInput,
    DeliverResponseInput,
    OperationResult,
)
from arakne.models.traces import RunTrace


def complete_ingestion(params: CompleteIngestionInput, trace: RunTrace) -> OperationResult:
    trace.completion_payload = params.model_dump()
    return OperationResult(ok=True)


def deliver_response(params: DeliverResponseInput, trace: RunTrace) -> OperationResult:
    trace.completion_payload = params.model_dump()
    return OperationResult(ok=True)


def complete_theme_update(
    params: CompleteThemeUpdateInput, trace: RunTrace
) -> OperationResult:
    trace.completion_payload = params.model_dump()
    return OperationResult(ok=True)
