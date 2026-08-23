from langgraph.graph import END, START, StateGraph

from config import MAX_CODE_ATTEMPTS
from pipeline.nodes.codegen import codegen
from pipeline.nodes.design import design
from pipeline.nodes.research import research
from pipeline.nodes.review import review
from pipeline.nodes.spec import spec
from pipeline.nodes.validate_execute import validate_execute
from pipeline.schemas import RunState


def _after_validate_execute(state: RunState) -> str:
    execution = state["execution"]
    if execution["status"] == "passed":
        return "review"
    if execution["attempt"] >= MAX_CODE_ATTEMPTS:
        return "give_up"
    return "codegen"


def _after_review(state: RunState) -> str:
    code = state["code"]
    if code["status"] == "passed":
        return "done"
    if code["attempt"] >= MAX_CODE_ATTEMPTS:
        return "give_up"
    return "codegen"


def _give_up(state: RunState) -> dict:
    execution = state["execution"]
    code = {**state["code"]}
    if execution["status"] != "passed":
        code["status"] = "failed_max_attempts"
    elif code["status"] != "passed":
        code["status"] = "failed_max_attempts"
    return {"code": code}


def build_graph():
    graph = StateGraph(RunState)
    graph.add_node("research", research)
    graph.add_node("design", design)
    graph.add_node("spec", spec)
    graph.add_node("codegen", codegen)
    graph.add_node("validate_execute", validate_execute)
    graph.add_node("review", review)
    graph.add_node("give_up", _give_up)

    graph.add_edge(START, "research")
    graph.add_edge("research", "design")
    graph.add_edge("design", "spec")
    graph.add_edge("spec", "codegen")
    graph.add_edge("codegen", "validate_execute")
    graph.add_conditional_edges(
        "validate_execute", _after_validate_execute, {"review": "review", "codegen": "codegen", "give_up": "give_up"}
    )
    graph.add_conditional_edges("review", _after_review, {"done": END, "codegen": "codegen", "give_up": "give_up"})
    graph.add_edge("give_up", END)

    return graph.compile()
