"""AI Game Design Pipeline — LangGraph multi-step graph.

Step 1: Genre Research — structured analysis of a game genre.
Step 2: GDD Generation — concrete game design document from the analysis.
"""

from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

from pipeline.schemas import GameDesignDocument, GenreAnalysis


# ---------------------------------------------------------------------------
# State: what flows through the graph
# ---------------------------------------------------------------------------
class PipelineState(TypedDict):
    genre: str
    analysis: GenreAnalysis | None
    gdd: GameDesignDocument | None


# ---------------------------------------------------------------------------
# Node: research_genre
# ---------------------------------------------------------------------------
RESEARCH_PROMPT = """\
You are an expert game designer specializing in hyper-casual and casual HTML5 \
browser games for portals like CrazyGames, Poki, and itch.io.

Analyze the genre: **{genre}**

Your analysis should be practical and opinionated — aimed at a small team that \
needs to ship a fun, retainable browser game in this genre within a month. \
Focus on what actually matters for player retention on web game portals, not \
theory.

Be specific. Name real techniques, real games, real numbers where possible. \
"Add juice" is not useful — "add 2-frame hit-freeze + radial particle burst \
on enemy death" is useful.
"""


def research_genre(state: PipelineState) -> PipelineState:
    """Call GPT-4o with structured output to produce a GenreAnalysis."""
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0.3,
        max_tokens=4096,
    )

    # .with_structured_output() makes the LLM return a Pydantic model directly
    structured_llm = llm.with_structured_output(GenreAnalysis)

    analysis = structured_llm.invoke(
        RESEARCH_PROMPT.format(genre=state["genre"])
    )

    return {"analysis": analysis}


# ---------------------------------------------------------------------------
# Node: generate_gdd
# ---------------------------------------------------------------------------
GDD_PROMPT = """\
You are an expert game designer writing a concrete Game Design Document for a \
hyper-casual / casual HTML5 browser game.

The target platforms are web portals like CrazyGames, Poki, and itch.io. The \
game must be buildable by a small team (1-3 devs) within one month.

Genre: **{genre}**

Here is the genre research to base your design on:
{analysis_json}

Design ONE specific game — not a template. Pick a clear creative direction and \
commit to it. The GDD should be specific enough that a developer could start \
building tomorrow.

Priorities:
- Instant fun in the first 3 seconds (no tutorials, no menus)
- Core loop must work with 1-2 inputs (mouse click / tap + optional direction)
- Visual style must be achievable with free assets or simple geometric art
- MVP-first: cut everything that isn't essential to the core loop
- Juice is mandatory, not optional — list specific techniques with parameters
"""


def generate_gdd(state: PipelineState) -> PipelineState:
    """Take the genre analysis and produce a concrete game design document."""
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0.7,
        max_tokens=4096,
    )

    structured_llm = llm.with_structured_output(GameDesignDocument)

    analysis_json = state["analysis"].model_dump_json(indent=2)

    gdd = structured_llm.invoke(
        GDD_PROMPT.format(genre=state["genre"], analysis_json=analysis_json)
    )

    return {"gdd": gdd}


# ---------------------------------------------------------------------------
# Graph wiring
# ---------------------------------------------------------------------------
def build_graph():
    """Build and compile the game design pipeline graph."""
    builder = StateGraph(PipelineState)

    builder.add_node("research_genre", research_genre)
    builder.add_node("generate_gdd", generate_gdd)

    builder.add_edge(START, "research_genre")
    builder.add_edge("research_genre", "generate_gdd")
    builder.add_edge("generate_gdd", END)

    return builder.compile()
