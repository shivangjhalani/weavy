"""Index summary-level grouped embeddings for better semantic retrieval."""

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


def _context(title: str, topics: list[str]) -> str:
    parts = []
    if title:
        parts.append(f"title: {title}")
    if topics:
        parts.append("topics: " + ", ".join(topics))
    return "\n".join(parts)


def main():
    summaries = load_summaries()
    client = get_chromadb_client(PERSIST_DIR)
    embed_fn = get_embed_fn("RETRIEVAL_DOCUMENT")

    try:
        client.delete_collection("structured_fields")
    except Exception:
        pass
    col = client.create_collection("structured_fields", embedding_function=embed_fn)

    ids, docs, metas = [], [], []
    for i, s in enumerate(summaries):
        title = str(s.get("title", "")).strip()
        topics = _list_items(s, "topics")
        context = _context(title, topics)

        key_learnings = _list_items(s, "key_learnings")
        active_questions = _list_items(s, "active_questions")
        memorable_quotes = _list_items(s, "memorable_quotes")
        mood = _list_items(s, "mood")

        # 1) Overview: title + topics + key learnings
        overview_parts = [context] if context else []
        if key_learnings:
            overview_parts.append("key_learnings: " + " | ".join(key_learnings))
        overview = "\n".join([p for p in overview_parts if p.strip()])
        if overview.strip():
            ids.append(f"journal_{i}_overview")
            docs.append(overview)
            metas.append({"embedding_for": "overview(title+topics+key_learnings)"})

        # 2) Questions: title + topics + active questions
        if active_questions:
            questions = "\n".join(
                [p for p in [context, "active_questions: " + " | ".join(active_questions)] if p.strip()]
            )
            ids.append(f"journal_{i}_questions")
            docs.append(questions)
            metas.append({"embedding_for": "questions(title+topics+active_questions)"})

        # 3) Quotes: title + topics + memorable quotes
        if memorable_quotes:
            quotes = "\n".join(
                [p for p in [context, "memorable_quotes: " + " | ".join(memorable_quotes)] if p.strip()]
            )
            ids.append(f"journal_{i}_quotes")
            docs.append(quotes)
            metas.append({"embedding_for": "quotes(title+topics+memorable_quotes)"})

        # 4) Mood: title + topics + mood
        if mood:
            mood_doc = "\n".join([p for p in [context, "mood: " + ", ".join(mood)] if p.strip()])
            ids.append(f"journal_{i}_mood")
            docs.append(mood_doc)
            metas.append({"embedding_for": "mood(title+topics+mood)"})

    BATCH = 80
    for start in range(0, len(ids), BATCH):
        end = start + BATCH
        col.upsert(ids=ids[start:end], documents=docs[start:end], metadatas=metas[start:end])
    print(f"Indexed {len(ids)} structured documents from {len(summaries)} journals.")


if __name__ == "__main__":
    main()
