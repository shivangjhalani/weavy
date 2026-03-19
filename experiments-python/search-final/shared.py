import json
import math
import re
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from litellm import embedding as litellm_embedding

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUMMARIES_DIR = PROJECT_ROOT / "private" / "summaries"
TOKEN_RE = re.compile(r"[a-z0-9]+")

load_dotenv(PROJECT_ROOT / ".env")


def load_summaries() -> list[dict]:
    summaries = []
    for path in sorted(SUMMARIES_DIR.glob("*_summary.json")):
        with path.open() as fh:
            summaries.append(json.load(fh))
    return summaries


def get_chromadb_client(persist_dir: str | Path) -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=str(persist_dir))


class LiteLLMEmbeddingFunction:
    """ChromaDB-compatible embedding function backed by litellm."""

    def __init__(self, model: str = "gemini/gemini-embedding-001"):
        self.model = model

    def name(self) -> str:
        return "litellm_embedding"

    def __call__(self, input: list[str]) -> list[list[float]]:
        response = litellm_embedding(model=self.model, input=input)
        return [item["embedding"] for item in response.data]

    def embed_documents(self, documents: list[str]) -> list[list[float]]:
        return self(documents)

    def embed_query(self, input: list[str] | str) -> list[list[float]] | list[float]:
        if isinstance(input, str):
            return self([input])[0]
        return self(input)


def get_embed_fn(task_type: str | None = None) -> LiteLLMEmbeddingFunction:
    return LiteLLMEmbeddingFunction()


def list_items(summary: dict, key: str) -> list[str]:
    value = summary.get(key, [])
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _summary_context(title: str, topics: list[str]) -> str:
    parts = []
    if title:
        parts.append(f"title: {title}")
    if topics:
        parts.append("topics: " + ", ".join(topics))
    return "\n".join(parts)


def build_structured_docs(summary: dict, journal_idx: int) -> list[tuple[str, str, dict]]:
    title = str(summary.get("title", "")).strip()
    date = str(summary.get("date", "")).strip()
    topics = list_items(summary, "topics")
    context = _summary_context(title, topics)
    rows: list[tuple[str, str, dict]] = []

    def append_doc(kind: str, body: str) -> None:
        body = body.strip()
        if not body:
            return
        rows.append(
            (
                f"journal_{journal_idx}_{kind}",
                body,
                {
                    "title": title or "?",
                    "date": date,
                    "kind": kind,
                },
            )
        )

    key_learnings = list_items(summary, "key_learnings")
    active_questions = list_items(summary, "active_questions")
    memorable_quotes = list_items(summary, "memorable_quotes")
    mood = list_items(summary, "mood")

    overview_parts = [context] if context else []
    if key_learnings:
        overview_parts.append("key_learnings: " + " | ".join(key_learnings))
    append_doc("overview", "\n".join([p for p in overview_parts if p.strip()]))

    if active_questions:
        append_doc(
            "questions",
            "\n".join([p for p in [context, "active_questions: " + " | ".join(active_questions)] if p.strip()]),
        )
    if memorable_quotes:
        append_doc(
            "quotes",
            "\n".join([p for p in [context, "memorable_quotes: " + " | ".join(memorable_quotes)] if p.strip()]),
        )
    if mood:
        append_doc("mood", "\n".join([p for p in [context, "mood: " + ", ".join(mood)] if p.strip()]))

    return rows


def transcript_prefix(summary: dict) -> str:
    title = str(summary.get("title", "")).strip()
    topics = ", ".join(list_items(summary, "topics"))
    return f"[{title} | {topics}]\n" if title or topics else ""


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def bm25_scores(query: str, docs: list[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
    if not docs:
        return []

    query_terms = list(dict.fromkeys(tokenize(query)))
    if not query_terms:
        return [0.0] * len(docs)

    doc_tokens = [tokenize(doc) for doc in docs]
    doc_lengths = [len(tokens) for tokens in doc_tokens]
    avg_doc_len = (sum(doc_lengths) / len(doc_lengths)) if doc_lengths else 1.0
    if avg_doc_len == 0:
        avg_doc_len = 1.0

    doc_freq: dict[str, int] = {}
    term_freqs: list[dict[str, int]] = []
    for tokens in doc_tokens:
        tf: dict[str, int] = {}
        for term in tokens:
            tf[term] = tf.get(term, 0) + 1
        term_freqs.append(tf)
        for term in tf:
            doc_freq[term] = doc_freq.get(term, 0) + 1

    total_docs = len(docs)
    scores: list[float] = []
    for doc_len, tf in zip(doc_lengths, term_freqs):
        score = 0.0
        for term in query_terms:
            freq = tf.get(term, 0)
            if freq == 0:
                continue
            n = doc_freq.get(term, 0)
            idf = math.log(1.0 + (total_docs - n + 0.5) / (n + 0.5))
            denom = freq + k1 * (1.0 - b + b * (doc_len / avg_doc_len))
            score += idf * ((freq * (k1 + 1.0)) / denom)
        scores.append(score)
    return scores


def minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi <= lo:
        return [1.0 if hi > 0 else 0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]
