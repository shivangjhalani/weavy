"""Index layer-2 transcript docs for hybrid search."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chonkie import Model2VecEmbeddings, SemanticChunker

from shared import get_chromadb_client, get_embed_fn, load_summaries, transcript_prefix

PERSIST_DIR = Path(__file__).parent / ".chromadb"
COLLECTION_NAME = "layer2_transcript_enriched_chunks_hybrid"


def main():
    summaries = load_summaries()
    client = get_chromadb_client(PERSIST_DIR)
    embed_fn = get_embed_fn("RETRIEVAL_DOCUMENT")

    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    col = client.create_collection(COLLECTION_NAME, embedding_function=embed_fn)

    chunker = SemanticChunker(
        embeddings=Model2VecEmbeddings(),
        threshold=0.5,
        chunk_size=512,
    )

    ids, docs, metas = [], [], []
    for i, summary in enumerate(summaries):
        transcript = str(summary.get("transcript", "")).strip()
        if not transcript:
            continue

        prefix = transcript_prefix(summary)
        chunks = chunker.chunk(transcript)
        for ci, chunk in enumerate(chunks):
            ids.append(f"journal_{i}_chunk_{ci}")
            docs.append(prefix + chunk.text)
            metas.append(
                {
                    "title": str(summary.get("title", "")).strip() or "?",
                    "date": str(summary.get("date", "")).strip(),
                    "chunk_index": ci,
                }
            )

    batch = 32
    for start in range(0, len(ids), batch):
        end = start + batch
        col.upsert(ids=ids[start:end], documents=docs[start:end], metadatas=metas[start:end])

    print(f"Indexed {len(ids)} transcript chunks from {len(summaries)} summaries.")


if __name__ == "__main__":
    main()
