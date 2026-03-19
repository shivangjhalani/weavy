import json
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from litellm import embedding as litellm_embedding

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SUMMARIES_DIR = PROJECT_ROOT / "private" / "summaries"

load_dotenv(PROJECT_ROOT / ".env")


def load_summaries() -> list[dict]:
    files = sorted(SUMMARIES_DIR.glob("*_summary.json"))
    summaries = []
    for f in files:
        with open(f) as fh:
            summaries.append(json.load(fh))
    return summaries


def get_chromadb_client(persist_dir: str | Path) -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=str(persist_dir))


class LiteLLMEmbeddingFunction:
    """ChromaDB-compatible embedding function backed by litellm.

    ChromaDB >= 1.5 calls embed_query() for query-time embeddings
    and __call__() for document-time embeddings.
    """

    def __init__(self, model: str = "gemini/gemini-embedding-001"):
        self.model = model

    def name(self) -> str:
        return "litellm-gemini"

    def __call__(self, input: list[str]) -> list[list[float]]:
        response = litellm_embedding(model=self.model, input=input)
        return [item["embedding"] for item in response.data]

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self(input)


def get_embed_fn(task_type: str | None = None) -> LiteLLMEmbeddingFunction:
    return LiteLLMEmbeddingFunction()
