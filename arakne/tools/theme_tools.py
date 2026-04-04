"""
Theme tools — theme map maintenance. Implemented in Phase 6.
"""

from falkordb import Graph

from arakne.models.tools import (
    CreateThemeInput,
    OperationResult,
    RetireThemeInput,
    UpdateThemeInput,
)
from arakne.models.traces import RunTrace
from arakne.store import themes as store_themes


def create_theme(
    graph: Graph, params: CreateThemeInput, trace: RunTrace  # noqa: ARG001
) -> OperationResult:
    return store_themes.create_theme(
        graph, params.name, params.state, params.anchors, params.status
    )


def update_theme(
    graph: Graph, params: UpdateThemeInput, trace: RunTrace  # noqa: ARG001
) -> OperationResult:
    return store_themes.update_theme(
        graph, params.name, params.new_state, params.new_anchors, params.new_status
    )


def retire_theme(
    graph: Graph, params: RetireThemeInput, trace: RunTrace  # noqa: ARG001
) -> OperationResult:
    return store_themes.retire_theme(graph, params.name)
