from pipeline.llm import get_generation_llm
from pipeline.retry import invoke_with_retry
from pipeline.schemas import GameDesignDocument, RunState
import json

PROMPT = """You are a game designer. Write a Game Design Document for a single-file, dependency-free HTML5 browser game.

Genre/concept: {brief}

Research on this genre:
{research}

Keep the scope tight enough to build as a single HTML file MVP: one core loop, a small, concrete control scheme, and a clear win/lose condition. Do not scope a game that needs external art or audio assets — everything must be proceduraly generated in-code.

Return a JSON object with these exact keys: title, core_loop, controls, mechanics, juice, mvp_scope, win_lose_condition. All values should be strings except mechanics and juice which should be arrays of strings.

Example format: {{"title": "...", "core_loop": "...", "controls": "...", "mechanics": [...], "juice": [...], "mvp_scope": "...", "win_lose_condition": "..."}}"""


REWORK_PROMPT = PROMPT + """

A human reviewed your previous draft and asked for changes:
{human_feedback}

Previous draft, for reference:
{previous_gdd}"""


def design(state: RunState) -> dict:
    research_artifact = state["research"]["artifact"]
    prior_design = state.get("design") or {}
    attempt = prior_design.get("attempt", 0) + 1

    if attempt == 1:
        prompt = PROMPT.format(brief=state["brief"], research=research_artifact)
    else:
        prompt = REWORK_PROMPT.format(
            brief=state["brief"],
            research=research_artifact,
            human_feedback=state.get("human_feedback") or "(no specific feedback given)",
            previous_gdd=prior_design.get("artifact"),
        )

    llm = get_generation_llm(temperature=0.7, node="design")
    raw = invoke_with_retry(lambda: llm.invoke(prompt))
    content = raw.content if hasattr(raw, "content") else str(raw)
    try:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            json_str = content[start:end]
            data = json.loads(json_str)
        else:
            raise ValueError("No JSON found in response")
    except Exception as e:
        # Return structured error state for parse failures - do NOT silently fallback
        return {
            "design": {
                "status": "failed_needs_rework",
                "attempt": attempt,
                "artifact": None,
                "review": None,
                "error": f"[syntax] JSON parse failed: {e}",
            }
        }
    result = GameDesignDocument(**data)
    return {
        "design": {
            "status": "passed",
            "attempt": attempt,
            "artifact": result.model_dump(),
            "review": None,
            "error": None,
        }
    }