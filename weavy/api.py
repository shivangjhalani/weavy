"""
Weavy public Python API.

This is the stable interface for programmatic use — benchmark harnesses,
scripts, and any caller that wants simple add/query semantics without
knowing about traces, sessions, or the FalkorDB graph internals.

    from weavy import WeavyMemory

    mem = WeavyMemory()
    mem.add("Had a long talk about career change today.")
    answer = mem.query("What have I been thinking about?")

graph_name selects a named FalkorDB graph (defaults to settings.GRAPH_NAME).
Different names give full graph-level isolation between instances — useful for
running multiple independent scenarios (e.g. benchmark runs) against the same
FalkorDB server.
"""

from __future__ import annotations

from datetime import datetime

from falkordb import Graph

from weavy.application.session_runs import run_add, run_query, run_session
from weavy.application.theme_runs import run_theme_update
from weavy.services.embedding import get_dimension
from weavy.store.client import get_graph
from weavy.store.system import init_system


class WeavyMemory:
    def __init__(self, graph_name: str | None = None) -> None:
        self._graph: Graph = get_graph(graph_name)
        init_system(self._graph, embedding_dim=get_dimension())

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def add(
        self,
        text: str,
        timestamp: datetime | None = None,
        context: str | None = None,
    ) -> str:
        """Ingest text into the memory graph.

        Returns the session_id of the created ingestion session.
        Raises RuntimeError if the ingestion agent fails.
        """
        trace = run_add(text, self._graph, timestamp=timestamp, context=context)
        if trace.status == "failed":
            raise RuntimeError(f"Ingestion failed: {trace.error}")
        return trace.session_id  # type: ignore[return-value]

    def query(
        self,
        question: str,
        context: str | None = None,
        query_time: datetime | None = None,
    ) -> str:
        """Query the memory graph. Returns the answer string.

        query_time overrides the agent's sense of "now" — pass it when the
        question logically belongs to a specific point in time (e.g. benchmark
        scenarios where question_date != today).

        Raises RuntimeError if the query agent fails.
        """
        trace = run_query(question, self._graph, context=context, query_time=query_time)
        if trace.status == "failed":
            raise RuntimeError(f"Query failed: {trace.error}")
        return (trace.completion_payload or {}).get("answer", "")

    def continue_session(self, session_id: str, message: str) -> str:
        """Append a message to an existing session and run the query agent.

        Useful for multi-turn interactions against a known session.
        Raises RuntimeError if the agent fails.
        """
        trace = run_session(session_id, "query", self._graph, message)
        if trace.status == "failed":
            raise RuntimeError(f"Session continuation failed: {trace.error}")
        return (trace.completion_payload or {}).get("answer", "")

    def update_themes(self) -> None:
        """Run the theme agent over the current graph.

        Raises RuntimeError if the theme agent fails.
        """
        trace = run_theme_update(self._graph)
        if trace.status == "failed":
            raise RuntimeError(f"Theme update failed: {trace.error}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Drop all graph data and reinitialize.

        Creates a clean slate — useful between independent benchmark scenarios.
        The WeavyMemory instance remains usable after reset.
        """
        self._graph.query("MATCH (n) DETACH DELETE n")
        init_system(self._graph, embedding_dim=get_dimension())
