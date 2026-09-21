# Minimal Playable-Ad Pipeline Skeleton

## Directory Structure
```
playable-ad-pipeline/
├── config.py              # API keys, model names, limits
├── pipeline/
│   ├── __init__.py
│   ├── graph.py           # LangGraph topology
│   ├── llm.py             # LLM factory (OpenRouter/Anthropic)
│   ├── schemas.py         # Pydantic models (GenreAnalysis, GDD, Spec, etc.)
│   ├── validate.py        # Static checks
│   ├── execute.py         # Playwright browser execution
│   ├── output.py          # Artifact persistence
│   ├── retry.py           # Retry logic
│   └── nodes/
│       ├── __init__.py
│       ├── research.py    # Genre analysis
│       ├── design.py      # GDD generation
│       ├── spec.py        # Implementation spec
│       ├── codegen.py     # HTML generation
│       ├── validate_execute.py  # Validation bridge
│       ├── review.py      # LLM review
│       └── human_review.py      # Optional human gate
├── vendor/
│   └── phaser.min.js      # Vendored Phaser
├── fixtures/
│   ├── known_good_game.html
│   ├── known_bad_game_asset_ref.html
│   ├── known_bad_game_delta_time.html
│   └── known_bad_game_console_error.html
├── tests/
│   ├── test_validate.py
│   ├── test_execute.py
│   ├── test_graph_routing.py
│   ├── test_human_review.py
│   └── test_pipeline_integration.py
├── pyproject.toml
└── .env.example
```

## Key Config (config.py)
```python
import os
from dotenv import load_dotenv
load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", ANTHROPIC_API_KEY)

GENERATION_MODEL = os.environ.get("GENERATION_MODEL", "anthropic/claude-sonnet-4")
REVIEW_MODEL = os.environ.get("REVIEW_MODEL", "anthropic/claude-3-haiku")

MAX_DESIGN_ATTEMPTS = int(os.environ.get("MAX_DESIGN_ATTEMPTS", "3"))
MAX_CODE_ATTEMPTS = int(os.environ.get("MAX_CODE_ATTEMPTS", "2"))
CODEGEN_MAX_TOKENS = int(os.environ.get("CODEGEN_MAX_TOKENS", "48000"))

HUMAN_REVIEW_GDD = os.environ.get("HUMAN_REVIEW_GDD", "true").lower() in ("1", "true", "yes")
```

## Minimal Graph (graph.py)
```python
from langgraph.graph import END, START, StateGraph
from pipeline.nodes import research, design, spec, codegen, validate_execute, review
from pipeline.schemas import RunState

def build_graph(checkpointer=None, human_review_gdd_enabled=None):
    graph = StateGraph(RunState)
    graph.add_node("research", research)
    graph.add_node("design", design)
    graph.add_node("spec", spec)
    graph.add_node("codegen", codegen)
    graph.add_node("validate_execute", validate_execute)
    graph.add_node("review", review)
    
    graph.add_edge(START, "research")
    graph.add_edge("research", "design")
    graph.add_edge("design", "spec")
    graph.add_edge("spec", "codegen")
    graph.add_edge("codegen", "validate_execute")
    
    def after_validate(state):
        if state["execution"]["status"] == "passed":
            return "review"
        if state["execution"]["attempt"] >= MAX_CODE_ATTEMPTS:
            return "give_up"
        return "codegen"
    
    def after_review(state):
        if state["code"]["status"] == "passed":
            return END
        if state["code"]["attempt"] >= MAX_CODE_ATTEMPTS:
            return "give_up"
        return "codegen"
    
    graph.add_conditional_edges("validate_execute", after_validate, 
        {"review": "review", "codegen": "codegen", "give_up": "give_up"})
    graph.add_conditional_edges("review", after_review,
        {"done": END, "codegen": "codegen", "give_up": "give_up"})
    
    return graph.compile(checkpointer=checkpointer)
```

## Usage
```python
from pipeline.graph import build_graph
import tempfile

graph = build_graph(human_review_gdd_enabled=False)
run_dir = tempfile.mkdtemp(prefix='playable_')

result = graph.invoke({
    "brief": "Endless runner with one-touch jump",
    "run_id": "demo",
    "run_dir": run_dir
}, {"recursion_limit": 50})

html = result["code"]["artifact"]["html"]
# Save standalone version with Phaser inlined
```