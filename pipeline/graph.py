"""Genre Research Agent — single-node LangGraph graph.

Takes a game genre as input, returns a structured GenreAnalysis.
This is Step 1 of the pipeline: get comfortable with LangGraph basics.
"""

from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

from pipeline.schemas import GenreAnalysis


# ---------------------------------------------------------------------------
# State: what flows through the graph
# ---------------------------------------------------------------------------
class ResearchState(TypedDict):
    genre: str
    analysis: GenreAnalysis | None


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


def research_genre(state: ResearchState) -> ResearchState:
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
# Graph wiring
# ---------------------------------------------------------------------------
def build_graph():
    """Build and compile the genre research graph."""
    builder = StateGraph(ResearchState)
    builder.add_node("research_genre", research_genre)
    builder.add_edge(START, "research_genre")
    builder.add_edge("research_genre", END)
    return builder.compile()
