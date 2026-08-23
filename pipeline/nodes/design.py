from pipeline.llm import get_generation_llm
from pipeline.schemas import GameDesignDocument, RunState

PROMPT = """You are a game designer. Write a Game Design Document for a single-file, \
dependency-free HTML5 browser game.

Genre/concept: {brief}

Research on this genre:
{research}

Keep the scope tight enough to build as a single HTML file MVP: one core loop, a small, \
concrete control scheme, and a clear win/lose condition. Do not scope a game that needs \
external art or audio assets — everything must be proceduraly generated in-code."""


def design(state: RunState) -> dict:
    research_artifact = state["research"]["artifact"]
    llm = get_generation_llm(temperature=0.7).with_structured_output(GameDesignDocument, method="function_calling")
    result: GameDesignDocument = llm.invoke(
        PROMPT.format(brief=state["brief"], research=research_artifact)
    )
    return {
        "design": {
            "status": "passed",
            "attempt": 1,
            "artifact": result.model_dump(),
            "review": None,
            "error": None,
        }
    }
