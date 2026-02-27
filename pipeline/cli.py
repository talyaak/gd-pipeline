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
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

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


def _display_hitl_prompt(interrupt_value: dict) -> str:
    """Show the GDD + review to the human and collect their response."""
    print("\n" + "=" * 60)
    print("  HUMAN REVIEW REQUIRED — Game Design Document")
    print("=" * 60)
    print(f"\n  Title:    {interrupt_value['title']}")
    print(f"  Pitch:    {interrupt_value['one_liner']}")
    print(f"  Score:    {interrupt_value['auto_review_score']}/10"
          f" ({'PASSED' if interrupt_value['auto_review_passed'] else 'MAX ATTEMPTS'})")
    print(f"  Attempt:  {interrupt_value['gdd_attempt']}")

    print("\n  Strengths:")
    for s in interrupt_value["strengths"]:
        print(f"    + {s}")

    if interrupt_value["issues"]:
        print("\n  Issues:")
        for i in interrupt_value["issues"]:
            print(f"    - {i}")

    if interrupt_value["suggestions"]:
        print("\n  Suggestions:")
        for s in interrupt_value["suggestions"]:
            print(f"    ~ {s}")

    print("\n" + "-" * 60)
    print("  Type 'approve' to proceed to implementation spec.")
    print("  Or type feedback to send the GDD back for rework.")
    print("-" * 60)

    response = input("\n> ").strip()
    if not response:
        response = "approve"
    return response


def main():
    load_dotenv()

    if len(sys.argv) < 2:
        print("Usage: python -m pipeline <genre>")
        print('Example: python -m pipeline "endless runner"')
        sys.exit(1)

    genre = " ".join(sys.argv[1:])

    # Build graph with checkpointer for HITL interrupts
    checkpointer = MemorySaver()
    graph = build_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "1"}}

    print(f"[pipeline] Researching genre: {genre} ...")

    # First invoke — runs until HITL interrupt (or completion if no interrupt)
    result = graph.invoke({"genre": genre}, config)

    # HITL loop: handle interrupts until the graph completes
    while True:
        state = graph.get_state(config)

        # Check if there are pending interrupts
        if not state.tasks or not any(
            t.interrupts for t in state.tasks
        ):
            break  # Graph is complete

        # Get the interrupt value and show to human
        interrupt_value = state.tasks[0].interrupts[0].value
        human_response = _display_hitl_prompt(interrupt_value)

        print(f"\n[pipeline] Resuming with: "
              f"{'APPROVED' if human_response.lower() in ('approve', 'y', 'yes', 'ok', 'lgtm') else 'REWORK'}")

        # Resume the graph with the human's response
        result = graph.invoke(Command(resume=human_response), config)

    # Extract final results
    final_state = graph.get_state(config).values
    analysis = final_state["analysis"]
    gdd = final_state["gdd"]
    gdd_review = final_state.get("gdd_review")
    gdd_attempt = final_state.get("gdd_attempt", 1)
    impl_spec = final_state["impl_spec"]
    impl_spec_review = final_state.get("impl_spec_review")
    impl_spec_attempt = final_state.get("impl_spec_attempt", 1)

    # Build combined output
    data = {
        "genre_analysis": analysis.model_dump(),
        "gdd": gdd.model_dump(),
        "gdd_review": gdd_review.model_dump() if gdd_review else None,
        "gdd_attempts": gdd_attempt,
        "implementation_spec": impl_spec.model_dump(),
        "impl_spec_review": (
            impl_spec_review.model_dump() if impl_spec_review else None
        ),
        "impl_spec_attempts": impl_spec_attempt,
    }

    # Summary
    print("\n" + "=" * 60)
    print(f"[pipeline] GDD: {gdd.title}")
    if gdd_review:
        print(f"[pipeline] GDD review: score {gdd_review.score}/10 "
              f"({'PASSED' if gdd_review.passed else 'FORCED'}) "
              f"after {gdd_attempt} attempt(s)")
    if impl_spec_review:
        print(f"[pipeline] Impl spec review: score {impl_spec_review.score}/10 "
              f"({'PASSED' if impl_spec_review.passed else 'FORCED'}) "
              f"after {impl_spec_attempt} attempt(s)")
    print(f"[pipeline] Impl spec: {len(impl_spec.entities)} entities, "
          f"{len(impl_spec.balance_tables)} balance tables, "
          f"{len(impl_spec.asset_manifest)} assets")
    print("=" * 60)
    print(json.dumps(data, indent=2))

    # Persist to output/
    out_path = _save(genre, data)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
