"""CLI entry point for the genre research agent.

Usage:
    python -m pipeline.cli "endless runner"
    python -m pipeline.cli "tower defense"
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from pipeline.graph import build_graph

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def _save(genre: str, data: dict) -> Path:
    """Save analysis JSON to output/<genre>_<timestamp>.json."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    slug = genre.lower().replace(" ", "_")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"{slug}_{ts}.json"
    path.write_text(json.dumps(data, indent=2))
    return path


def main():
    load_dotenv()

    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.cli <genre>")
        print('Example: python -m pipeline.cli "endless runner"')
        sys.exit(1)

    genre = " ".join(sys.argv[1:])
    print(f"Researching genre: {genre}\n")

    graph = build_graph()
    result = graph.invoke({"genre": genre})

    analysis = result["analysis"]
    data = analysis.model_dump()

    # Pretty-print the structured output
    print(json.dumps(data, indent=2))

    # Persist to output/
    out_path = _save(genre, data)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
