"""LifeOS Memo — detect themes and patterns across journal entries.

Usage: devenv shell -- python scripts/memo.py
Full implementation in Phase 4.
"""
from lifeos.core.config import get_config
from lifeos.agent.harness import AgentHarness  # noqa: F401 — verify import works


def main():
    config = get_config()
    print("[memo] LifeOS memo agent")
    print(f"[memo] Graph: {config.graph_name}")
    print("[memo] Stub — full implementation in Phase 4")


if __name__ == "__main__":
    main()
