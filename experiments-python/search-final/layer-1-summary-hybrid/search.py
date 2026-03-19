"""Search layer-1 summary docs with dense + BM25 hybrid scoring."""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared import bm25_scores, get_chromadb_client, get_embed_fn, minmax

ALPHA = 0.6
PERSIST_DIR = Path(__file__).parent / ".chromadb"
COLLECTION_NAME = "layer1_summary_structured_hybrid"


def main():
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        print('Usage: uv run search.py "your query here"')
        sys.exit(1)

    client = get_chromadb_client(PERSIST_DIR)
    embed_fn = get_embed_fn("RETRIEVAL_QUERY")
    col = client.get_collection(COLLECTION_NAME, embedding_function=embed_fn)

    all_rows = col.get(include=["documents", "metadatas"])
    ids = all_rows.get("ids", [])
    docs = all_rows.get("documents", [])
    metas = all_rows.get("metadatas", [])
    if not docs:
        print("No results.")
        return

    dense_results = col.query(query_texts=[query], n_results=len(ids))
    dense_ids = dense_results.get("ids", [[]])[0]
    dense_dists = dense_results.get("distances", [[]])[0]
    dense_raw_map = {doc_id: 1.0 / (1.0 + dist) for doc_id, dist in zip(dense_ids, dense_dists)}

    dense_raw = [dense_raw_map.get(doc_id, 0.0) for doc_id in ids]
    bm25_raw = bm25_scores(query, docs)
    dense_norm = minmax(dense_raw)
    bm25_norm = minmax(bm25_raw)
    hybrid_scores = [ALPHA * d + (1.0 - ALPHA) * b for d, b in zip(dense_norm, bm25_norm)]

    grouped_counts: dict[str, int] = defaultdict(int)
    grouped_best: dict[str, tuple[float, float, float, str, dict]] = {}
    for doc, meta, hybrid, dense, bm25 in zip(docs, metas, hybrid_scores, dense_norm, bm25_norm):
        clean_meta = meta or {}
        title = clean_meta.get("title", "?")
        grouped_counts[title] += 1
        best = grouped_best.get(title)
        if best is None or hybrid > best[0]:
            grouped_best[title] = (hybrid, dense, bm25, doc, clean_meta)

    ranked = sorted(grouped_best.items(), key=lambda x: x[1][0], reverse=True)[:5]
    print(f"Top {len(ranked)} hybrid grouped results for: {query}\n")
    for rank, (title, (hybrid, dense, bm25, doc, meta)) in enumerate(ranked, start=1):
        kind = meta.get("kind", "?")
        best_of = grouped_counts.get(title, 1)
        print(f"[{rank:02d}] score={hybrid:.4f} dense={dense:.4f} bm25={bm25:.4f}")
        print(f"title: {title}")
        print(f"for: grouped_structured_hybrid(alpha={ALPHA}, best_of={best_of}, kind={kind})")
        print(f"content:\n{doc}\n")


if __name__ == "__main__":
    main()
