from pipeline.llm import get_review_llm
from pipeline.schemas import GenreAnalysis, RunState

PROMPT = """You are a game design researcher. Given a game genre/concept, analyze it concisely.

Genre/concept: {brief}

Identify the core mechanics, typical juice/feedback techniques, how progression/difficulty \
usually scales, common mistakes that make implementations of this genre feel bad, and 1-3 \
well-known reference games."""


def research(state: RunState) -> dict:
    llm = get_review_llm().with_structured_output(GenreAnalysis, method="function_calling")
    result: GenreAnalysis = llm.invoke(PROMPT.format(brief=state["brief"]))
    return {
        "research": {
            "status": "passed",
            "attempt": 1,
            "artifact": result.model_dump(),
            "review": None,
            "error": None,
        }
    }
