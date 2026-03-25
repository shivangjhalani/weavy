"""LifeOS Evaluation — RAGAS quality metrics for query responses.

Usage: devenv shell -- python scripts/eval.py
Full implementation in Phase 5.
"""
from lifeos.core.config import get_config
from lifeos.agent.harness import AgentHarness  # noqa: F401 — verify import works


def main():
    config = get_config()
    print("[eval] LifeOS evaluation harness")
    print(f"[eval] Graph: {config.graph_name}")
    print("[eval] Stub — full implementation in Phase 5")


if __name__ == "__main__":
    main()
