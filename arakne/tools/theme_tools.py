"""
Theme tools — theme map maintenance.
"""

from falkordb import Graph

from arakne.models.tools import (
    CreateThemeInput,
    OperationResult,
    RetireThemeInput,
    UpdateThemeInput,
)
from arakne.store import themes as store_themes


def create_theme(graph: Graph, params: CreateThemeInput) -> OperationResult:
    return store_themes.create_theme(
        graph, params.name, params.state, params.anchors, params.status
    )


def update_theme(graph: Graph, params: UpdateThemeInput) -> OperationResult:
    return store_themes.update_theme(
        graph, params.name, params.new_state, params.new_anchors, params.new_status
    )


def retire_theme(graph: Graph, params: RetireThemeInput) -> OperationResult:
    return store_themes.retire_theme(graph, params.name)
