"""Run test queries against all search experiments and dump raw results to JSON."""

import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SEARCH_DIR = Path(__file__).resolve().parent
SENTENCE_CHUNKS_DIR = SEARCH_DIR / "transcript-level" / "sentence-chunks"
SUMMARIES_DIR = ROOT / "private" / "summaries"

INDEX_SCRIPTS = {
    "full_blob": (SEARCH_DIR / "summary-level" / "full-blob", "index.py", None),
    "structured_fields": (SEARCH_DIR / "summary-level" / "structured-fields", "index.py", None),
    "grouped_structured": (SEARCH_DIR / "summary-level" / "structured-fields-grouped", "index.py", None),
    "semantic_chunks": (SEARCH_DIR / "transcript-level" / "semantic-chunks", "index.py", None),
    "enriched_chunks": (SEARCH_DIR / "transcript-level" / "enriched-semantic-chunks", "index.py", None),
    "sentence_chunks_512": (SENTENCE_CHUNKS_DIR, "index.py", {"CHUNK_SIZE": "512"}),
    "sentence_chunks_1024": (SENTENCE_CHUNKS_DIR, "index.py", {"CHUNK_SIZE": "1024"}),
    "sentence_chunks_2048": (SENTENCE_CHUNKS_DIR, "index.py", {"CHUNK_SIZE": "2048"}),
}

EXPERIMENTS = {
    "full_blob": (SEARCH_DIR / "summary-level" / "full-blob", "search.py"),
    "structured_fields": (SEARCH_DIR / "summary-level" / "structured-fields", "search.py"),
    "semantic_chunks": (SEARCH_DIR / "transcript-level" / "semantic-chunks", "search.py"),
    "enriched_chunks": (SEARCH_DIR / "transcript-level" / "enriched-semantic-chunks", "search.py"),
    "grouped_structured": (SEARCH_DIR / "summary-level" / "structured-fields-grouped", "search.py"),
    "grouped_semantic_chunks": (SEARCH_DIR / "transcript-level" / "semantic-chunks", "search_grouped.py"),
    "grouped_enriched_chunks": (SEARCH_DIR / "transcript-level" / "enriched-semantic-chunks", "search_grouped.py"),
    # Sentence chunks (Chonkie SentenceChunker) — multiple chunk sizes for comparison
    "sentence_chunks_512": (SENTENCE_CHUNKS_DIR, "search.py", {"CHUNK_SIZE": "512"}),
    "sentence_chunks_1024": (SENTENCE_CHUNKS_DIR, "search.py", {"CHUNK_SIZE": "1024"}),
    "sentence_chunks_2048": (SENTENCE_CHUNKS_DIR, "search.py", {"CHUNK_SIZE": "2048"}),
    "grouped_sentence_chunks_512": (SENTENCE_CHUNKS_DIR, "search_grouped.py", {"CHUNK_SIZE": "512"}),
    "grouped_sentence_chunks_1024": (SENTENCE_CHUNKS_DIR, "search_grouped.py", {"CHUNK_SIZE": "1024"}),
    "grouped_sentence_chunks_2048": (SENTENCE_CHUNKS_DIR, "search_grouped.py", {"CHUNK_SIZE": "2048"}),
}

# ── Test Queries with Ground Truth ──────────────────────────────────────
# Queries are loaded from an external file to keep personal/sensitive data out of git.
def _load_queries(path: Path) -> list[tuple[str, str, list[str]]]:
    if not path.exists():
        # Fallback for visibility (or error handling)
        return []
    with open(path) as fh:
        data = json.load(fh)
    return [(q["query"], q["category"], q["expected_titles"]) for q in data]


QUERIES_PATH = SEARCH_DIR / "eval_queries.json"
QUERIES = _load_queries(QUERIES_PATH)


if not QUERIES:
    print(f"\n[WARNING] No evaluation queries found in {QUERIES_PATH}")
    print("Ensure you have created it from template/private data.")
    # In a real environment, you might raise SystemExit(1) here.


# Per-search timeout (seconds); increase if Gemini embedding API is slow or rate-limited
SEARCH_TIMEOUT = int(os.environ.get("EVAL_SEARCH_TIMEOUT", "90"))


def _title_to_indices() -> dict[str, list[int]]:
    summary_paths = sorted(SUMMARIES_DIR.glob("*_summary.json"))
    if not summary_paths:
        raise RuntimeError(f"No summary files found at {SUMMARIES_DIR}")
    mapping: dict[str, list[int]] = defaultdict(list)
    for idx, path in enumerate(summary_paths):
        with open(path) as fh:
            summary = json.load(fh)
        title = str(summary.get("title", "")).strip()
        if title:
            mapping[title].append(idx)
    return dict(mapping)


TITLE_TO_INDICES = _title_to_indices()


def resolve_expected_indices(query: str, expected_titles: list[str]) -> list[int]:
    missing: list[str] = []
    resolved: list[int] = []
    for title in expected_titles:
        indices = TITLE_TO_INDICES.get(title)
        if not indices:
            missing.append(title)
            continue
        resolved.extend(indices)
    if missing:
        missing_fmt = "; ".join(missing)
        raise ValueError(
            f"Ground-truth title(s) missing from corpus for query '{query}': {missing_fmt}"
        )
    return sorted(set(resolved))


def run_search(
    experiment_dir: Path,
    query: str,
    script: str = "search.py",
    env: dict | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a search and return completed process with stdout/stderr."""
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        ["uv", "run", script, query],
        cwd=str(experiment_dir),
        env=full_env,
        capture_output=True,
        text=True,
        timeout=SEARCH_TIMEOUT,
    )


def parse_results(raw: str) -> list[dict]:
    """Parse search output into structured results."""
    results = []
    lines = raw.strip().split("\n")
    current = {}
    content_lines = []
    in_content = False
    for line in lines:
        if line.startswith("[") and "] dist=" in line:
            if current:
                current["content"] = "\n".join(content_lines).strip()
                results.append(current)
                content_lines = []
                in_content = False
            rank_str = line.split("]")[0].strip("[")
            dist_str = line.split("dist=")[1]
            current = {"rank": int(rank_str), "distance": float(dist_str)}
        elif line.startswith("title: ") and not in_content:
            current["title"] = line[7:].strip()
        elif line.startswith("for: "):
            current["embedding_for"] = line[5:]
        elif line.startswith("content:"):
            in_content = True
            rest = line[8:].strip()
            if rest:
                content_lines.append(rest)
        elif in_content and current:
            content_lines.append(line)
    if current:
        current["content"] = "\n".join(content_lines).strip()
        results.append(current)
    return results


# Parallel workers; reduce if hitting embedding API rate limits or timeouts
MAX_WORKERS = int(os.environ.get("EVAL_MAX_WORKERS", "8"))


def _run_one(
    q_key: str,
    exp_name: str,
    query: str,
    exp_dir: Path,
    exp_script: str,
    exp_env: dict | None,
) -> tuple[str, str, dict]:
    """Run a single search and return structured result payload."""
    try:
        completed = run_search(exp_dir, query, exp_script, exp_env)
        raw = (completed.stdout or "") + (completed.stderr or "")
        parsed = parse_results(raw)
        payload = {
            "raw": raw,
            "parsed": parsed,
            "returncode": completed.returncode,
        }
        if completed.returncode != 0:
            payload["error"] = f"non-zero return code: {completed.returncode}"
        return (q_key, exp_name, payload)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return (
            q_key,
            exp_name,
            {
                "raw": stdout + stderr,
                "parsed": [],
                "returncode": None,
                "error": f"timeout after {SEARCH_TIMEOUT}s",
            },
        )
    except Exception as exc:
        return (
            q_key,
            exp_name,
            {
                "raw": "",
                "parsed": [],
                "returncode": None,
                "error": f"exception: {type(exc).__name__}: {exc}",
            },
        )


def _corpus_hash() -> str:
    """Compute a hash of the corpus based on sorted summary file paths, sizes, and mtimes."""
    h = hashlib.sha256()
    for p in sorted(SUMMARIES_DIR.glob("*_summary.json")):
        st = p.stat()
        h.update(f"{p.name}:{st.st_size}:{st.st_mtime_ns}\n".encode())
    return h.hexdigest()[:16]


def rebuild_indexes():
    total = len(INDEX_SCRIPTS)
    for i, (name, (idx_dir, script, env_vars)) in enumerate(INDEX_SCRIPTS.items(), 1):
        print(f"[{i}/{total}] Rebuilding {name}...", flush=True)
        env = {**os.environ, **(env_vars or {})}
        result = subprocess.run(
            ["uv", "run", script],
            cwd=str(idx_dir),
            env=env,
        )
        if result.returncode != 0:
            print(f"FATAL: index build failed for {name} (exit {result.returncode})")
            raise SystemExit(1)
    corpus_hash = _corpus_hash()
    print(f"All indexes rebuilt. Corpus hash: {corpus_hash}", flush=True)


def main():
    if "--skip-index" not in sys.argv:
        rebuild_indexes()
    else:
        print("Skipping index rebuild (--skip-index)")

    all_results = {}
    for q_idx, (query, category, expected_titles) in enumerate(QUERIES):
        expected_indices = resolve_expected_indices(query, expected_titles)
        q_key = f"q{q_idx:02d}"
        all_results[q_key] = {
            "query": query,
            "category": category,
            "expected_titles": expected_titles,
            "expected_indices": expected_indices,
            "experiments": {},
        }

    tasks = []
    for q_idx, (query, _category, _expected_titles) in enumerate(QUERIES):
        q_key = f"q{q_idx:02d}"
        for exp_name, exp_spec in EXPERIMENTS.items():
            if len(exp_spec) == 3:
                exp_dir, exp_script, exp_env = exp_spec
            else:
                exp_dir, exp_script = exp_spec
                exp_env = None
            tasks.append((q_key, exp_name, query, exp_dir, exp_script, exp_env))

    total = len(tasks)
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(_run_one, qk, en, q, ed, es, ee): (en, q[:50])
            for qk, en, q, ed, es, ee in tasks
        }
        for fut in as_completed(futures):
            exp_name, query_preview = futures[fut]
            q_key, exp_name, payload = fut.result()
            all_results[q_key]["experiments"][exp_name] = payload
            done += 1
            print(f"[{done}/{total}] {exp_name}: {query_preview}...", flush=True)

    out_path = SEARCH_DIR / "eval_raw_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)

    failures = []
    for q_key, q_data in all_results.items():
        for exp_name, payload in q_data["experiments"].items():
            if payload.get("error"):
                failures.append((q_key, exp_name, payload["error"]))

    print(f"\nDone. Results saved to {out_path}")
    if failures:
        print(f"Detected {len(failures)} failed experiment runs. First 10:")
        for q_key, exp_name, error in failures[:10]:
            print(f"  {q_key} | {exp_name}: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
