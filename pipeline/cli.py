import argparse
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
    final_state = graph.invoke(
        {"brief": args.brief, "run_id": run_dir.name, "run_dir": str(run_dir)},
        {"recursion_limit": 50},
    )

    # research/design/spec run exactly once (no rework loop), so it's safe for the
    # CLI to persist them post-hoc from final_state; code/execution/review loop and
    # persist themselves per-attempt from inside their nodes (see codegen.py,
    # validate_execute.py, review.py) so no attempt's evidence is lost to a later one.
    for i, step in enumerate(["research", "design", "spec"], start=1):
        result = final_state.get(step, {})
        out = stage_dir(run_dir, i, step, result.get("attempt", 1))
        write_json(out, step, result.get("artifact") or {})

    steps = ["research", "design", "spec", "code", "execution"]
    for i, step in enumerate(steps, start=1):
        result = final_state.get(step, {})
        status = result.get("status")
        print(f"  [{i}/5] {step}: {status} (attempt {result.get('attempt')})")
        if result.get("error"):
            print(f"        error: {result['error']}")

    code = final_state.get("code", {})
    if code.get("artifact", {}).get("html"):
        write_text(run_dir, "game.html", code["artifact"]["html"])

    summary = {step: final_state.get(step, {}).get("status") for step in steps}
    write_json(run_dir, "pipeline_summary", summary)

    if code.get("status") != "passed":
        print(f"\nPipeline did not produce a passing game.html (status: {code.get('status')})", file=sys.stderr)
        sys.exit(1)

    print(f"\ngame.html written to {run_dir / 'game.html'}")


if __name__ == "__main__":
    main()
