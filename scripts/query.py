"""LifeOS Query — ask questions about your journal.

Usage: devenv shell -- python scripts/query.py
Full implementation in Phase 3.
"""
from lifeos.core.config import get_config
from lifeos.agent.harness import AgentHarness  # noqa: F401 — verify import works


def main():
    config = get_config()
    print("[query] LifeOS query agent")
    print(f"[query] Graph: {config.graph_name}")
    print("[query] Stub — full implementation in Phase 3")


if __name__ == "__main__":
    main()
