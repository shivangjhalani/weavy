"""Index summaries as one blob using summary-level fields only."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared import get_chromadb_client, get_embed_fn, load_summaries

PERSIST_DIR = Path(__file__).parent / ".chromadb"


def _list_items(summary: dict, key: str) -> list[str]:
    value = summary.get(key, [])
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def build_text(summary: dict) -> str:
    parts = []

    title = str(summary.get("title", "")).strip()
    if title:
        parts.append(f"title: {title}")

    topics = _list_items(summary, "topics")
    if topics:
        parts.append("topics: " + ", ".join(topics))

    key_learnings = _list_items(summary, "key_learnings")
    if key_learnings:
        parts.append("key_learnings: " + " | ".join(key_learnings))

    active_questions = _list_items(summary, "active_questions")
    if active_questions:
        parts.append("active_questions: " + " | ".join(active_questions))

    memorable_quotes = _list_items(summary, "memorable_quotes")
    if memorable_quotes:
        parts.append("memorable_quotes: " + " | ".join(memorable_quotes))

    mood = _list_items(summary, "mood")
    if mood:
        parts.append("mood: " + ", ".join(mood))

    return "\n".join(parts)


def main():
    summaries = load_summaries()
    client = get_chromadb_client(PERSIST_DIR)
    embed_fn = get_embed_fn("RETRIEVAL_DOCUMENT")

    try:
        client.delete_collection("full_blob")
    except Exception:
        pass
    col = client.create_collection("full_blob", embedding_function=embed_fn)

    ids, docs, metas = [], [], []
    for i, s in enumerate(summaries):
        text = build_text(s)
        if not text.strip():
            continue
        ids.append(f"journal_{i}")
        docs.append(text)
        metas.append({"embedding_for": "full_blob"})

    BATCH = 80
    for start in range(0, len(ids), BATCH):
        end = start + BATCH
        col.upsert(ids=ids[start:end], documents=docs[start:end], metadatas=metas[start:end])
    print(f"Indexed {len(ids)} journals into full_blob collection.")


if __name__ == "__main__":
    main()
