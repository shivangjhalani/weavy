import pytest
from pathlib import Path


@pytest.fixture
def tmp_transcript_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for TranscriptStore tests."""
    d = tmp_path / "transcripts"
    d.mkdir()
    return d


@pytest.fixture
def mock_env(monkeypatch):
    """Monkeypatch environment variables for config tests."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("FALKORDB_HOST", "localhost")
    monkeypatch.setenv("FALKORDB_PORT", "6379")
    monkeypatch.setenv("GRAPH_NAME", "test-lifeos")
    monkeypatch.setenv("TRANSCRIPT_DIR", "data/transcripts")
    return monkeypatch
