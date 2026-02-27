"""CLI entry point for the game design pipeline.

Usage:
    python -m pipeline "endless runner"
    python -m pipeline "tower defense"
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
        print("Usage: python -m pipeline <genre>")
        print('Example: python -m pipeline "endless runner"')
        sys.exit(1)

    genre = " ".join(sys.argv[1:])

    print(f"[1/3] Researching genre: {genre} ...")
    graph = build_graph()
    result = graph.invoke({"genre": genre})

    analysis = result["analysis"]
    gdd = result["gdd"]
    impl_spec = result["impl_spec"]

    # Build combined output
    data = {
        "genre_analysis": analysis.model_dump(),
        "gdd": gdd.model_dump(),
        "implementation_spec": impl_spec.model_dump(),
    }

    # Summary
    print(f"[2/3] GDD generated: {gdd.title}")
    print(f"[3/3] Impl spec: {len(impl_spec.entities)} entities, "
          f"{len(impl_spec.balance_tables)} balance tables, "
          f"{len(impl_spec.asset_manifest)} assets")
    print("=" * 60)
    print(json.dumps(data, indent=2))

    # Persist to output/
    out_path = _save(genre, data)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
