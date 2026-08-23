from langgraph.types import interrupt

from pipeline.schemas import RunState


def human_review_gdd(state: RunState) -> dict:
    decision = interrupt(
        {
            "kind": "gdd_approval",
            "gdd": state["design"]["artifact"],
        }
    )
    approved = bool(decision.get("approved"))
    return {
        "human_feedback": decision.get("feedback") if not approved else None,
        "design": {
            **state["design"],
            "status": "passed" if approved else "failed_needs_rework",
        },
    }
