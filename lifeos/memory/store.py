import json
from pathlib import Path
from typing import Any


class TranscriptStore:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, transcript_id: str, data: dict[str, Any]) -> Path:
        path = self.base_dir / f"{transcript_id}.json"
        path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
        return path

    def load(self, transcript_id: str) -> dict[str, Any] | None:
        path = self.base_dir / f"{transcript_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def exists(self, transcript_id: str) -> bool:
        return (self.base_dir / f"{transcript_id}.json").exists()
