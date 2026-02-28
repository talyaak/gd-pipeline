"""CLI entry point for the game design pipeline.

Usage:
    python -m pipeline "endless runner"
    python -m pipeline "tower defense"
"""

import sys
import warnings

# Suppress noisy langchain/pydantic v1 deprecation warnings
warnings.filterwarnings("ignore", message=".*Pydantic V1.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain")

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from pipeline import output
from pipeline.graph import build_graph


def _display_hitl_prompt(interrupt_value: dict) -> str:
    """Save the GDD for review, show summary + review, and collect response."""
    # Save full GDD to a convenience file for human review
    draft_path = output.save("02_gdd", "gdd_for_review.json", interrupt_value["gdd"])

    print("\n" + "=" * 60)
    print("  HUMAN REVIEW REQUIRED — Game Design Document")
    print("=" * 60)
    print(f"\n  Title:    {interrupt_value['title']}")
    print(f"  Pitch:    {interrupt_value['one_liner']}")
    print(f"  Score:    {interrupt_value['auto_review_score']}/10"
          f" ({'PASSED' if interrupt_value['auto_review_passed'] else 'MAX ATTEMPTS'})")
    print(f"  Attempt:  {interrupt_value['gdd_attempt']}")
    print(f"\n  >>> Full GDD saved to: {draft_path}")
    print("  >>> Open it in your editor to review before approving.")

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

    # Initialize output directory for this run
    run_dir = output.init_run(genre)
    print(f"[pipeline] Output directory: {output.rel(run_dir)}")

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
    code = final_state.get("code")
    code_review = final_state.get("code_review")
    code_attempt = final_state.get("code_attempt", 1)

    # Build combined output (metadata only — code is in separate .html files)
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
        "code_review": code_review.model_dump() if code_review else None,
        "code_attempts": code_attempt,
    }

    # Save combined summary
    summary_path = output.save(".", "summary.json", data)

    # Print concise summary — no JSON walls
    print("\n" + "=" * 60)
    print(f"  Game:       {gdd.title}")
    print(f"  Pitch:      {gdd.one_liner}")
    if gdd_review:
        print(f"  GDD:        score {gdd_review.score}/10 "
              f"({'PASSED' if gdd_review.passed else 'FORCED'}) "
              f"· {gdd_attempt} attempt(s)")
    if impl_spec_review:
        print(f"  Impl spec:  score {impl_spec_review.score}/10 "
              f"({'PASSED' if impl_spec_review.passed else 'FORCED'}) "
              f"· {impl_spec_attempt} attempt(s)")
    if code_review:
        print(f"  Code:       score {code_review.score}/10 "
              f"({'PASSED' if code_review.passed else 'FORCED'}) "
              f"· {code_attempt} attempt(s)")
    print(f"  Entities:   {len(impl_spec.entities)}")
    print(f"  Balance:    {len(impl_spec.balance_tables)} tables")
    print(f"  Assets:     {len(impl_spec.asset_manifest)}")
    if code:
        print(f"  Game file:  04_code/attempt_{code_attempt}/game.html")
    print("=" * 60)
    print(f"\n  All artifacts → {output.rel(output.run_dir())}/")
    print(f"  Full summary → {output.rel(summary_path)}")


if __name__ == "__main__":
    main()
