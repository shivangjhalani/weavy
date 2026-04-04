"""
Eval runner — executes scenarios against the real harness and captures results.
Implemented in Phase 9.
"""

from arakne.evals.scenarios import Scenario


def run_scenario(scenario: Scenario) -> dict:
    """Execute a scenario through the real harness and return a result dict."""
    raise NotImplementedError


def run_suite(scenarios: list[Scenario]) -> list[dict]:
    raise NotImplementedError
