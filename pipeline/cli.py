import argparse
import json
import sys

from pipeline.graph import build_graph
from pipeline.output import new_run_dir, stage_dir, write_json, write_text


def main() -> None:
    parser = argparse.ArgumentParser(prog="pipeline", description="Generate a playable HTML5 game from a genre/concept.")
    parser.add_argument("brief", help="Game genre or concept, e.g. 'endless runner'")
    args = parser.parse_args()

    run_dir = new_run_dir(args.brief)
    print(f"Run directory: {run_dir}")

    graph = build_graph()
    final_state = graph.invoke({"brief": args.brief, "run_id": run_dir.name})

    steps = ["research", "design", "spec", "code"]
    for i, step in enumerate(steps, start=1):
        result = final_state.get(step, {})
        out = stage_dir(run_dir, i, step, result.get("attempt", 1))
        if step == "code":
            html = result.get("artifact", {}).get("html", "")
            write_text(out, "game.html", html)
            write_text(run_dir, "game.html", html)
        else:
            write_json(out, step, result.get("artifact", {}) or {})
        status = result.get("status")
        print(f"  [{i}/4] {step}: {status}")
        if result.get("error"):
            print(f"        error: {result['error']}")

    summary = {step: final_state.get(step, {}).get("status") for step in steps}
    write_json(run_dir, "pipeline_summary", summary)

    if final_state.get("code", {}).get("status") != "passed":
        print("Pipeline did not produce a passing game.html", file=sys.stderr)
        sys.exit(1)

    print(f"\ngame.html written to {run_dir / 'game.html'}")


if __name__ == "__main__":
    main()
