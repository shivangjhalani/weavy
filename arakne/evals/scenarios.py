"""
Eval scenario format — typed scenario definitions for harness eval runs.
Implemented in Phase 9.
"""

from typing import Any, Literal

from pydantic import BaseModel


class DeterministicAssertion(BaseModel):
    check: str
    expected: Any


class JudgeRubric(BaseModel):
    dimension: str
    description: str


class Scenario(BaseModel):
    id: str
    mode: Literal["ingestion", "query", "theme", "chat"]
    description: str
    canonical_fixtures: list[str]  # transcript/chat ids or file paths
    initial_graph_state: dict[str, Any] | None = None
    user_question: str | None = None
    expected_behaviors: list[str] = []
    deterministic_assertions: list[DeterministicAssertion] = []
    judge_rubrics: list[JudgeRubric] = []
