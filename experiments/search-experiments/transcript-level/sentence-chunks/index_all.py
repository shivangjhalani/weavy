"""Build sentence-chunk indexes for all chunk sizes (512, 1024, 2048).

Run from this directory: uv run index_all.py
Or from search-experiments: uv run transcript-level/sentence-chunks/index_all.py
"""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

CHUNK_SIZES = [512, 1024, 2048]


def main():
    for size in CHUNK_SIZES:
        print(f"\n--- Indexing sentence chunks (size={size}) ---")
        result = subprocess.run(
            ["uv", "run", "index.py"],
            cwd=str(SCRIPT_DIR),
            env={**os.environ, "CHUNK_SIZE": str(size)},
        )
        if result.returncode != 0:
            print(f"Failed to index chunk_size={size}", file=sys.stderr)
            sys.exit(1)
    print("\nDone. All sentence chunk indexes built.")


if __name__ == "__main__":
    main()
