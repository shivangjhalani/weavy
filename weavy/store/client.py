from functools import lru_cache

from falkordb import FalkorDB, Graph

from weavy.config import settings


@lru_cache(maxsize=1)
def _get_db() -> FalkorDB:
    return FalkorDB(host=settings.FALKORDB_HOST, port=settings.FALKORDB_PORT)


def get_graph(graph_name: str | None = None) -> Graph:
    """Connect to FalkorDB and return the named graph. Fails loudly on error."""
    return _get_db().select_graph(graph_name or settings.GRAPH_NAME)
