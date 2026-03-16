"""Search structured-field summary embeddings. Usage: uv run search.py "query" """

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared import get_chromadb_client, get_embed_fn

PERSIST_DIR = Path(__file__).parent / ".chromadb"

TITLE_RE = re.compile(r"title:\s*(.+?)(?:\n|$)")


def extract_journal_title(doc: str) -> str:
    m = TITLE_RE.search(doc)
    return m.group(1).strip() if m else doc[:60]


def main():
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        print("Usage: uv run search.py \"your query here\"")
        sys.exit(1)

    client = get_chromadb_client(PERSIST_DIR)
    embed_fn = get_embed_fn("RETRIEVAL_QUERY")
    col = client.get_collection("structured_fields", embedding_function=embed_fn)

    results = col.query(query_texts=[query], n_results=50)
    docs = results.get("documents", [[]])[0]
    dists = results.get("distances", [[]])[0]

    if not docs:
        print("No results.")
        return

    journals: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for doc, dist in zip(docs, dists):
        title = extract_journal_title(doc)
        journals[title].append((dist, doc))

    ranked = []
    for title, entries in journals.items():
        best_dist, best_doc = min(entries, key=lambda x: x[0])
        ranked.append((best_dist, title, best_doc, len(entries)))
    ranked.sort(key=lambda x: x[0])

    top = ranked[:5]
    print(f"Top {len(top)} results for: {query}\n")
    for rank, (dist, title, doc, count) in enumerate(top, start=1):
        print(f"[{rank:02d}] dist={dist:.4f}")
        print(f"title: {title}")
        print(f"for: structured(best_of={count})")
        print(f"content:\n{doc}\n")


if __name__ == "__main__":
    main()
