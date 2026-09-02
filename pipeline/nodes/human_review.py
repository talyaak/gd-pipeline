from langgraph.types import interrupt

import config as config_module
from pipeline.schemas import RunState


def human_review_gdd(state: RunState) -> dict:
    if not config_module.HUMAN_REVIEW_GDD:
        # Automatically approve GDD when human review is disabled
        approved = True
        feedback = None
    else:
        decision = interrupt(
            {
                "kind": "gdd_approval",
                "gdd": state["design"]["artifact"],
            }
        )
        approved = bool(decision.get("approved"))
        feedback = decision.get("feedback") if not approved else None
    return {
        "human_feedback": feedback,
        "design": {
            **state["design"],
            "status": "passed" if approved else "failed_needs_rework",
        },
    }
