from falkordb import FalkorDB, Graph

from weavy.config import settings


def get_graph(graph_name: str | None = None) -> Graph:
    """Connect to FalkorDB and return the named graph. Fails loudly on error."""
    name = graph_name or settings.GRAPH_NAME
    db = FalkorDB(host=settings.FALKORDB_HOST, port=settings.FALKORDB_PORT)
    return db.select_graph(name)
