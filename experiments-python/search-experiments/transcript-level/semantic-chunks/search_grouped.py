"""Search transcript semantic chunks, grouped by journal. Usage: uv run search_grouped.py "query" """

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared import get_chromadb_client, get_embed_fn

PERSIST_DIR = Path(__file__).parent / ".chromadb"


def main():
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        print('Usage: uv run search_grouped.py "your query here"')
        sys.exit(1)

    client = get_chromadb_client(PERSIST_DIR)
    embed_fn = get_embed_fn("RETRIEVAL_QUERY")
    col = client.get_collection("semantic_chunks", embedding_function=embed_fn)

    results = col.query(query_texts=[query], n_results=50)
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    if not docs:
        print("No results.")
        return

    journals: dict[str, list[tuple[float, str, dict]]] = defaultdict(list)
    for doc, meta, dist in zip(docs, metas, dists):
        title = (meta or {}).get("title", "?")
        journals[title].append((dist, doc, meta or {}))

    ranked = []
    for title, entries in journals.items():
        best_dist, best_doc, best_meta = min(entries, key=lambda x: x[0])
        ranked.append((best_dist, best_doc, best_meta, title, len(entries)))
    ranked.sort(key=lambda x: x[0])

    top = ranked[:5]
    print(f"Top {len(top)} results for: {query}\n")
    for rank, (dist, doc, meta, title, count) in enumerate(top, start=1):
        chunk_index = meta.get("chunk_index", "?")
        embedding_for = f"grouped_semantic_chunk(best_of={count})"
        print(f"[{rank:02d}] dist={dist:.4f}")
        print(f"title: {title}")
        print(f"for: {embedding_for}")
        print(f"content:\n{doc}\n")


if __name__ == "__main__":
    main()
