"""Run transcript-level experiments for passage-level retrieval evaluation.

This differs from eval_run.py in one important way:
- it stores raw chunk-level ranked results (no journal deduplication)

Expected query file format (JSON list):
[
  {
    "query": "when did I feel most determined to build something?",
    "category": "question",
    "targets": [
      {"title": "Commitment to My App Idea", "snippet": "I WILL MAKE THIS FKIN APPP"}
    ]
  }
]

Use queries.template.json as the starting point.
"""

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PASSAGE_DIR = Path(__file__).resolve().parent
SEARCH_EXPERIMENTS_DIR = PASSAGE_DIR.parent
ROOT = SEARCH_EXPERIMENTS_DIR.parent.parent
TRANSCRIPT_DIR = SEARCH_EXPERIMENTS_DIR / "transcript-level"
SENTENCE_CHUNKS_DIR = TRANSCRIPT_DIR / "sentence-chunks"
SUMMARIES_DIR = ROOT / "private" / "summaries"
RESULTS_PATH = PASSAGE_DIR / "raw_results.json"
QUERIES_PATH = Path(
    os.environ.get("PASSAGE_EVAL_QUERIES", str(PASSAGE_DIR / "queries.json"))
)
TOP_N = int(os.environ.get("PASSAGE_EVAL_TOP_N", "50"))
MAX_WORKERS = int(os.environ.get("PASSAGE_EVAL_MAX_WORKERS", "8"))

sys.path.insert(0, str(SEARCH_EXPERIMENTS_DIR))

from shared import get_chromadb_client, get_embed_fn


INDEX_SCRIPTS = {
    "semantic_chunks": (TRANSCRIPT_DIR / "semantic-chunks", "index.py", None),
    "enriched_chunks": (TRANSCRIPT_DIR / "enriched-semantic-chunks", "index.py", None),
    "sentence_chunks_512": (SENTENCE_CHUNKS_DIR, "index.py", {"CHUNK_SIZE": "512"}),
    "sentence_chunks_1024": (SENTENCE_CHUNKS_DIR, "index.py", {"CHUNK_SIZE": "1024"}),
    "sentence_chunks_2048": (SENTENCE_CHUNKS_DIR, "index.py", {"CHUNK_SIZE": "2048"}),
}


EXPERIMENTS = {
    "semantic_chunks": {
        "persist_dir": TRANSCRIPT_DIR / "semantic-chunks" / ".chromadb",
        "collection": "semantic_chunks",
    },
    "enriched_chunks": {
        "persist_dir": TRANSCRIPT_DIR / "enriched-semantic-chunks" / ".chromadb",
        "collection": "enriched_semantic_chunks",
    },
    "sentence_chunks_512": {
        "persist_dir": SENTENCE_CHUNKS_DIR / ".chromadb",
        "collection": "sentence_chunks_512",
    },
    "sentence_chunks_1024": {
        "persist_dir": SENTENCE_CHUNKS_DIR / ".chromadb",
        "collection": "sentence_chunks_1024",
    },
    "sentence_chunks_2048": {
        "persist_dir": SENTENCE_CHUNKS_DIR / ".chromadb",
        "collection": "sentence_chunks_2048",
    },
}


def _corpus_hash() -> str:
    h = hashlib.sha256()
    for p in sorted(SUMMARIES_DIR.glob("*_summary.json")):
        st = p.stat()
        h.update(f"{p.name}:{st.st_size}:{st.st_mtime_ns}\n".encode())
    return h.hexdigest()[:16]


def _load_queries(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"Passage eval query file not found: {path}. "
            "Create it from queries.template.json"
        )
    with open(path) as fh:
        queries = json.load(fh)
    if not isinstance(queries, list) or not queries:
        raise ValueError("Passage eval query file must be a non-empty JSON list")

    normalized: list[dict] = []
    for i, q in enumerate(queries):
        if not isinstance(q, dict):
            raise ValueError(f"Query row {i} must be an object")
        query = str(q.get("query", "")).strip()
        category = str(q.get("category", "misc")).strip() or "misc"
        targets = q.get("targets", [])
        if not query:
            raise ValueError(f"Query row {i} has empty `query`")
        if not isinstance(targets, list) or not targets:
            raise ValueError(f"Query row {i} must define a non-empty `targets` list")

        clean_targets: list[dict] = []
        for ti, target in enumerate(targets):
            if not isinstance(target, dict):
                raise ValueError(f"Query row {i} target {ti} must be an object")
            title = str(target.get("title", "")).strip()
            snippet = str(target.get("snippet", "")).strip()
            date = str(target.get("date", "")).strip()
            if not title:
                raise ValueError(f"Query row {i} target {ti} requires `title`")
            if not snippet:
                raise ValueError(f"Query row {i} target {ti} requires `snippet`")
            clean_targets.append({"title": title, "snippet": snippet, "date": date})

        normalized.append({"query": query, "category": category, "targets": clean_targets})

    return normalized


def rebuild_indexes() -> None:
    total = len(INDEX_SCRIPTS)
    for i, (name, (idx_dir, script, env_vars)) in enumerate(INDEX_SCRIPTS.items(), 1):
        print(f"[{i}/{total}] Rebuilding {name}...", flush=True)
        env = {**os.environ, **(env_vars or {})}
        result = subprocess.run(["uv", "run", script], cwd=str(idx_dir), env=env)
        if result.returncode != 0:
            print(f"FATAL: index build failed for {name} (exit {result.returncode})")
            raise SystemExit(1)
    print(f"All transcript indexes rebuilt. Corpus hash: {_corpus_hash()}", flush=True)


def query_chunks(exp_name: str, query: str, n_results: int) -> list[dict]:
    cfg = EXPERIMENTS[exp_name]
    client = get_chromadb_client(cfg["persist_dir"])
    embed_fn = get_embed_fn("RETRIEVAL_QUERY")
    col = client.get_collection(cfg["collection"], embedding_function=embed_fn)

    result = col.query(query_texts=[query], n_results=n_results)
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    dists = result.get("distances", [[]])[0]
    ids = result.get("ids", [[]])[0]

    rows: list[dict] = []
    for rank, (doc, meta, dist, chunk_id) in enumerate(zip(docs, metas, dists, ids), start=1):
        meta = meta or {}
        rows.append(
            {
                "rank": rank,
                "distance": float(dist),
                "id": chunk_id,
                "title": str(meta.get("title", "")).strip(),
                "date": str(meta.get("date", "")).strip(),
                "chunk_index": meta.get("chunk_index"),
                "start_char": meta.get("start_char"),
                "end_char": meta.get("end_char"),
                "embedding_for": exp_name,
                "content": doc,
            }
        )
    return rows


def _run_one(q_key: str, exp_name: str, query: str) -> tuple[str, str, dict]:
    try:
        parsed = query_chunks(exp_name, query, TOP_N)
        return q_key, exp_name, {"parsed": parsed, "returncode": 0}
    except Exception as exc:
        return (
            q_key,
            exp_name,
            {
                "parsed": [],
                "returncode": None,
                "error": f"exception: {type(exc).__name__}: {exc}",
            },
        )


def main() -> None:
    if "--skip-index" not in sys.argv:
        rebuild_indexes()
    else:
        print("Skipping index rebuild (--skip-index)")

    queries = _load_queries(QUERIES_PATH)

    all_results: dict[str, dict] = {}
    for q_idx, q in enumerate(queries):
        q_key = f"q{q_idx:02d}"
        all_results[q_key] = {
            "query": q["query"],
            "category": q["category"],
            "targets": q["targets"],
            "experiments": {},
        }

    tasks: list[tuple[str, str, str]] = []
    for q_idx, q in enumerate(queries):
        q_key = f"q{q_idx:02d}"
        for exp_name in EXPERIMENTS:
            tasks.append((q_key, exp_name, q["query"]))

    total = len(tasks)
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_run_one, qk, exp, query): (exp, query[:50]) for qk, exp, query in tasks}
        for fut in as_completed(futures):
            exp_name, query_preview = futures[fut]
            q_key, exp_name, payload = fut.result()
            all_results[q_key]["experiments"][exp_name] = payload
            done += 1
            print(f"[{done}/{total}] {exp_name}: {query_preview}...", flush=True)

    output = {
        "meta": {
            "top_n": TOP_N,
            "queries_path": str(QUERIES_PATH),
            "experiments": list(EXPERIMENTS.keys()),
            "corpus_hash": _corpus_hash(),
        },
        "queries": all_results,
    }

    with open(RESULTS_PATH, "w") as fh:
        json.dump(output, fh, indent=2)

    failures = []
    for q_key, q_data in all_results.items():
        for exp_name, payload in q_data["experiments"].items():
            if payload.get("error"):
                failures.append((q_key, exp_name, payload["error"]))

    print(f"\nDone. Passage-level results saved to {RESULTS_PATH}")
    if failures:
        print(f"Detected {len(failures)} failed experiment runs. First 10:")
        for q_key, exp_name, error in failures[:10]:
            print(f"  {q_key} | {exp_name}: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
