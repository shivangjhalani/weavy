"""Search layer-2 transcript docs with dense + BM25 hybrid scoring."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared import bm25_scores, get_chromadb_client, get_embed_fn, minmax

ALPHA = 0.6
PERSIST_DIR = Path(__file__).parent / ".chromadb"
COLLECTION_NAME = "layer2_transcript_enriched_chunks_hybrid"


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

    ranked_rows = sorted(
        zip(hybrid_scores, dense_norm, bm25_norm, docs, metas),
        key=lambda x: x[0],
        reverse=True,
    )[:5]

    print(f"Top {len(ranked_rows)} hybrid results for: {query}\n")
    for rank, (hybrid, dense, bm25, doc, meta) in enumerate(ranked_rows, start=1):
        chunk_index = (meta or {}).get("chunk_index", "?")
        title = (meta or {}).get("title", "?")
        print(f"[{rank:02d}] score={hybrid:.4f} dense={dense:.4f} bm25={bm25:.4f}")
        print(f"title: {title}")
        print(f"for: enriched_chunk_hybrid(alpha={ALPHA}, index={chunk_index})")
        print(f"content:\n{doc}\n")


if __name__ == "__main__":
    main()
