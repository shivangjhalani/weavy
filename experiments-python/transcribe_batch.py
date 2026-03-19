import json
import os
from pathlib import Path

import litellm
from dotenv import load_dotenv

litellm.drop_params = True

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Load .env from project root (where .env lives)
load_dotenv(PROJECT_ROOT / ".env")

EXTENSIONS = {".m4a"}


def _resolve_path_from_env(key: str, default: str) -> Path:
    """Resolve a path from env: supports absolute paths, ~/home, and relative (from project root)."""
    value = (os.getenv(key) or default).strip()
    if not value:
        value = default
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def main():
    input_dir = _resolve_path_from_env("INPUT_AUDIO_DIR", "./input")
    output_dir = _resolve_path_from_env("OUTPUT_DIR", "./output")

    if not input_dir.is_dir():
        raise SystemExit(f"Input directory does not exist or is not a directory: {input_dir}")

    files = sorted(f for f in input_dir.rglob("*") if f.is_file() and f.suffix.lower() in EXTENSIONS)
    if not files:
        print("No audio files found")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    model = os.getenv("MODEL", "groq/whisper-large-v3-turbo")
    language = os.getenv("LANGUAGE") or None
    prompt = os.getenv("TRANS_PROMPT") or None
    response_format = os.getenv("RESPONSE_FORMAT", "verbose_json")
    temperature = float(os.getenv("TEMPERATURE", "0"))
    granularities = [s.strip() for s in os.getenv("TIMESTAMP_GRANULARITIES", "segment,word").split(",") if s.strip()]

    for f in files:
        rel = f.relative_to(input_dir)
        out_base = output_dir / rel.with_suffix("")
        out_base.parent.mkdir(parents=True, exist_ok=True)
        txt_path = out_base.with_suffix(".txt")
        json_path = out_base.with_suffix(".json")

        if txt_path.exists() and json_path.exists():
            print(f"Skip {rel}")
            continue

        kwargs = {"file": open(f, "rb"), "model": model, "response_format": response_format, "temperature": temperature}
        if language:
            kwargs["language"] = language
        if prompt:
            kwargs["prompt"] = prompt
        if response_format == "verbose_json" and granularities:
            kwargs["timestamp_granularities"] = granularities

        with kwargs["file"] as fp:
            kwargs["file"] = fp
            response = litellm.transcription(**kwargs)

        text = getattr(response, "text", "") or ""
        data = response.model_dump() if hasattr(response, "model_dump") else {"text": text}

        txt_path.write_text((text or "").strip() + "\n", encoding="utf-8")
        json_path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"Done {rel}")


if __name__ == "__main__":
    main()
