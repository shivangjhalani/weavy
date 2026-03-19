"""Search layer-1 summary docs with grouped_structured ranking."""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared import get_chromadb_client, get_embed_fn

PERSIST_DIR = Path(__file__).parent / ".chromadb"
COLLECTION_NAME = "layer1_summary_structured"


def main():
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        print('Usage: uv run search.py "your query here"')
        sys.exit(1)

    client = get_chromadb_client(PERSIST_DIR)
    embed_fn = get_embed_fn("RETRIEVAL_QUERY")
    col = client.get_collection(COLLECTION_NAME, embedding_function=embed_fn)

    results = col.query(query_texts=[query], n_results=50)
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    if not docs:
        print("No results.")
        return

    grouped: dict[str, list[tuple[float, str, dict]]] = defaultdict(list)
    for doc, meta, dist in zip(docs, metas, dists):
        title = (meta or {}).get("title", "?")
        grouped[title].append((dist, doc, meta or {}))

    ranked = []
    for title, entries in grouped.items():
        best_dist, best_doc, best_meta = min(entries, key=lambda x: x[0])
        ranked.append((best_dist, best_doc, best_meta, title, len(entries)))
    ranked.sort(key=lambda x: x[0])

    top = ranked[:5]
    print(f"Top {len(top)} grouped results for: {query}\n")
    for rank, (dist, doc, meta, title, count) in enumerate(top, start=1):
        kind = meta.get("kind", "?")
        print(f"[{rank:02d}] dist={dist:.4f}")
        print(f"title: {title}")
        print(f"for: grouped_structured(best_of={count}, kind={kind})")
        print(f"content:\n{doc}\n")


if __name__ == "__main__":
    main()
