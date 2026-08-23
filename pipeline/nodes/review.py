from pathlib import Path

from pipeline.llm import get_review_llm
from pipeline.output import stage_dir, write_json
from pipeline.schemas import CodeReview, RunState

PROMPT = """Review this generated game's code for spec fidelity and quality. Runtime \
correctness has ALREADY been proven by executing it in a real browser (see evidence below) \
— do not re-guess at whether it runs; focus on whether it matches the design intent and is \
reasonably well-structured. Keep your response to at most 5 issues total, under 400 tokens.

Game Design Document:
{gdd}

Implementation Spec:
{spec}

Execution evidence (already verified, not your job to re-check):
- Loaded cleanly: {loaded}
- Canvas rendered: {canvas_rendered}
- Input produced an observable change: {input_response}

Generated code:
{html}
"""


def review(state: RunState) -> dict:
    gdd = state["design"]["artifact"]
    impl_spec = state["spec"]["artifact"]
    code = state["code"]
    exec_artifact = state["execution"]["artifact"]

    llm = get_review_llm().with_structured_output(CodeReview, method="function_calling")
    result: CodeReview = llm.invoke(
        PROMPT.format(
            gdd=gdd,
            spec=impl_spec,
            loaded=exec_artifact["loaded"],
            canvas_rendered=exec_artifact["canvas_rendered"],
            input_response=exec_artifact["input_response_detected"],
            html=code["artifact"]["html"][:12000],
        )
    )

    passed = result.score >= 7
    out_dir = stage_dir(Path(state["run_dir"]), 4, "code", code["attempt"])
    write_json(out_dir, "review", result.model_dump())

    return {
        "code": {
            **code,
            "status": "passed" if passed else "failed_needs_rework",
            "review": result.model_dump(),
        }
    }
