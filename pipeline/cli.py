"""CLI entry point for the genre research agent.

Usage:
    python -m pipeline.cli "endless runner"
    python -m pipeline.cli "tower defense"
"""

import json
import sys

from dotenv import load_dotenv

from pipeline.graph import build_graph


def main():
    load_dotenv()

    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.cli <genre>")
        print('Example: python -m pipeline.cli "endless runner"')
        sys.exit(1)

    genre = " ".join(sys.argv[1:])
    print(f"Researching genre: {genre}\n")

    graph = build_graph()
    result = graph.invoke({"genre": genre, "analysis": None})

    analysis = result["analysis"]

    # Pretty-print the structured output
    print(json.dumps(analysis.model_dump(), indent=2))


if __name__ == "__main__":
    main()
