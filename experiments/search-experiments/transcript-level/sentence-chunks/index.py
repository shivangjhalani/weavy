"""Chunk transcripts with SentenceChunker (sentence-boundary preserving), then index with Gemini.

Chunk size is configurable via CHUNK_SIZE env var (default 512 tokens).
See: https://docs.chonkie.ai/oss/chunkers/sentence-chunker
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from chonkie import SentenceChunker

from shared import get_chromadb_client, get_embed_fn, load_summaries

PERSIST_DIR = Path(__file__).parent / ".chromadb"
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "512"))
COLLECTION_NAME = f"sentence_chunks_{CHUNK_SIZE}"


def main():
    summaries = load_summaries()
    client = get_chromadb_client(PERSIST_DIR)
    embed_fn = get_embed_fn("RETRIEVAL_DOCUMENT")

    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    col = client.create_collection(COLLECTION_NAME, embedding_function=embed_fn)

    chunker = SentenceChunker(
        tokenizer="character",
        chunk_size=CHUNK_SIZE,
        chunk_overlap=64,
        min_sentences_per_chunk=1,
    )

    ids, docs, metas = [], [], []
    for i, s in enumerate(summaries):
        transcript = s.get("transcript", "").strip()
        if not transcript:
            continue

        chunks = chunker.chunk(transcript)
        for ci, chunk in enumerate(chunks):
            ids.append(f"journal_{i}_chunk_{ci}")
            docs.append(chunk.text)
            metas.append({
                "date": s["date"],
                "title": s["title"],
                "chunk_index": ci,
                "start_char": chunk.start_index,
                "end_char": chunk.end_index,
            })

    BATCH = 10
    for start in range(0, len(ids), BATCH):
        end = start + BATCH
        col.upsert(ids=ids[start:end], documents=docs[start:end], metadatas=metas[start:end])
    print(f"Indexed {len(ids)} sentence chunks (size={CHUNK_SIZE}) from {len(summaries)} journals.")


if __name__ == "__main__":
    main()
