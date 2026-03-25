"""LifeOS Ingestion — transcribe audio and build semantic graph.

Usage: devenv shell -- python scripts/ingest.py
Full implementation in Phase 2.
"""
from lifeos.core.config import get_config
from lifeos.agent.harness import AgentHarness  # noqa: F401 — verify import works


def main():
    config = get_config()
    print("[ingest] LifeOS ingestion pipeline")
    print(f"[ingest] Transcript dir: {config.transcript_dir}")
    print(f"[ingest] FalkorDB: {config.falkordb_host}:{config.falkordb_port}")
    print(f"[ingest] Graph: {config.graph_name}")
    print("[ingest] Stub — full implementation in Phase 2")


if __name__ == "__main__":
    main()
