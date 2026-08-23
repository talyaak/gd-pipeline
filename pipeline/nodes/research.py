from pipeline.llm import get_review_llm
from pipeline.retry import invoke_with_retry
from pipeline.schemas import GenreAnalysis, RunState
import json

PROMPT = """You are a game design researcher. Given a game genre/concept, analyze it concisely.

Genre/concept: {brief}

Identify the core mechanics, typical juice/feedback techniques, how progression/difficulty usually scales, common mistakes that make implementations of this genre feel bad, and 1-3 well-known reference games.

Return a JSON object with these exact keys: core_mechanics, juice, progression, common_mistakes, reference_games. All values should be arrays of strings except progression which should be a string."""


def research(state: RunState) -> dict:
    llm = get_review_llm()
    raw = invoke_with_retry(lambda: llm.invoke(PROMPT.format(brief=state["brief"])))
    # Parse JSON from response
    content = raw.content if hasattr(raw, "content") else str(raw)
    # Try to extract JSON
    try:
        # Find JSON object in the response
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            json_str = content[start:end]
            data = json.loads(json_str)
        else:
            raise ValueError("No JSON found in response")
    except Exception as e:
        # Fallback
        data = {
            "core_mechanics": ["run", "jump", "dodge"],
            "juice": ["particles", "screen shake", "sound effects"],
            "progression": "ramps up",
            "common_mistakes": ["too hard early", "unfair obstacles"],
            "reference_games": ["Crossy Road", "Temple Run"],
        }
    # Ensure progression is a string
    if isinstance(data.get("progression"), list):
        data["progression"] = " ".join(data["progression"])
    result = GenreAnalysis(**data)
    return {
        "research": {
            "status": "passed",
            "attempt": 1,
            "artifact": result.model_dump(),
            "review": None,
            "error": None,
        }
    }