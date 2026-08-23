from langgraph.graph import END, START, StateGraph

from pipeline.nodes.codegen import codegen
from pipeline.nodes.design import design
from pipeline.nodes.research import research
from pipeline.nodes.spec import spec
from pipeline.schemas import RunState


def build_graph():
    graph = StateGraph(RunState)
    graph.add_node("research", research)
    graph.add_node("design", design)
    graph.add_node("spec", spec)
    graph.add_node("codegen", codegen)

    graph.add_edge(START, "research")
    graph.add_edge("research", "design")
    graph.add_edge("design", "spec")
    graph.add_edge("spec", "codegen")
    graph.add_edge("codegen", END)

    return graph.compile()
