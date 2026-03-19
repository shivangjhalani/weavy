"""Index layer-1 summary docs for hybrid search."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared import build_structured_docs, get_chromadb_client, get_embed_fn, load_summaries

PERSIST_DIR = Path(__file__).parent / ".chromadb"
COLLECTION_NAME = "layer1_summary_structured_hybrid"


def main():
    summaries = load_summaries()
    client = get_chromadb_client(PERSIST_DIR)
    embed_fn = get_embed_fn("RETRIEVAL_DOCUMENT")

    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    col = client.create_collection(COLLECTION_NAME, embedding_function=embed_fn)

    ids, docs, metas = [], [], []
    for i, summary in enumerate(summaries):
        for row_id, doc, meta in build_structured_docs(summary, i):
            ids.append(row_id)
            docs.append(doc)
            metas.append(meta)

    batch = 80
    for start in range(0, len(ids), batch):
        end = start + batch
        col.upsert(ids=ids[start:end], documents=docs[start:end], metadatas=metas[start:end])

    print(f"Indexed {len(ids)} docs from {len(summaries)} summaries into {COLLECTION_NAME}.")


if __name__ == "__main__":
    main()
