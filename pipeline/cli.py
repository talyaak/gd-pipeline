import argparse
import sys

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from pipeline.graph import build_graph
from pipeline.output import new_run_dir, stage_dir, write_json, write_text


def _prompt_gdd_approval(gdd: dict) -> dict:
    print("\n--- Human review: Game Design Document ---")
    print(f"Title: {gdd.get('title')}")
    print(f"Core loop: {gdd.get('core_loop')}")
    print(f"Controls: {gdd.get('controls')}")
    print(f"Mechanics: {gdd.get('mechanics')}")
    print(f"MVP scope: {gdd.get('mvp_scope')}")
    print(f"Win/lose: {gdd.get('win_lose_condition')}")
    answer = input("Approve this GDD? [y/N]: ").strip().lower()
    if answer == "y":
        return {"approved": True}
    feedback = input("What should change? ").strip()
    return {"approved": False, "feedback": feedback}


def _run_graph(graph, initial_input: dict, run_config: dict) -> dict:
    state = graph.invoke(initial_input, run_config)
    while state.get("__interrupt__"):
        payload = state["__interrupt__"][0].value
        if payload.get("kind") == "gdd_approval":
            answer = _prompt_gdd_approval(payload["gdd"])
        else:
            raise ValueError(f"Unhandled interrupt kind: {payload.get('kind')}")
        state = graph.invoke(Command(resume=answer), run_config)
    return state


def main() -> None:
    parser = argparse.ArgumentParser(prog="pipeline", description="Generate a playable HTML5 game from a genre/concept.")
    parser.add_argument("brief", help="Game genre or concept, e.g. 'endless runner'")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    run_dir = new_run_dir(args.brief)
    print(f"Run directory: {run_dir}")

    checkpoint_path = str(run_dir / "checkpoint.sqlite")
    run_config = {"configurable": {"thread_id": run_dir.name}, "recursion_limit": 50}

    with SqliteSaver.from_conn_string(checkpoint_path) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        final_state = _run_graph(
            graph,
            {"brief": args.brief, "run_id": run_dir.name, "run_dir": str(run_dir)},
            run_config,
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
