from pathlib import Path
from pipeline.llm import get_review_llm
from pipeline.output import stage_dir, write_json
from pipeline.retry import invoke_with_retry
from pipeline.schemas import CodeReview, RunState
import json

PROMPT = """Review this generated game's code for spec fidelity and quality. Runtime correctness has ALREADY been proven by executing it in a real browser (see evidence below) — do not re-guess at whether it runs; focus on whether it matches the design intent and is reasonably well-structured. Keep your response to at most 5 issues total, under 400 tokens.

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

Return a JSON object with these exact keys: score (integer 1-10), spec_fidelity_issues (array of strings), quality_issues (array of strings), strengths (array of strings)."""

def review(state: RunState) -> dict:
    gdd = state["design"]["artifact"]
    impl_spec = state["spec"]["artifact"]
    code = state["code"]
    exec_artifact = state.get("execution", {}).get("artifact")
    loaded = False
    canvas_rendered = False
    input_response_detected = False
    raw = None
    if exec_artifact is not None:
        loaded = exec_artifact["loaded"]
        canvas_rendered = exec_artifact["canvas_rendered"]
        input_response_detected = exec_artifact["input_response_detected"]
        llm = get_review_llm(node="review")
        prompt = PROMPT.format(gdd=gdd, spec=impl_spec, loaded=loaded, canvas_rendered=canvas_rendered, input_response=input_response_detected, html=code["artifact"]["html"])
        raw = invoke_with_retry(lambda: llm.invoke(prompt), node="review")
        # LLM invoke returns an object with .content attribute (e.g., SimpleNamespace or BaseMessage)
        raw_content = raw.content if hasattr(raw, "content") else str(raw)
        try:
            start = raw_content.find("{")
            end = raw_content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = raw_content[start:end]
                data = json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")
        except Exception as e:
            # A malformed review response must never be treated as a passing review —
            # force a rework attempt instead of fabricating a score.
            data = {
                "score": 1,
                "spec_fidelity_issues": [],
                "quality_issues": [f"Review unavailable: model returned unparseable output ({e})"],
                "strengths": [],
            }
        result = CodeReview(**data)
    elif exec_artifact is None:
        # Execution did not produce an artifact (likely due to static validation failure)
        # We'll fail the review to trigger a rework of the codegen stage
        data = {
            "score": 1,
            "spec_fidelity_issues": [f'Static validation failed: {state.get("execution", {}).get("error", "Unknown error")}'],
            "quality_issues": [],
            "strengths": [],
        }
        result = CodeReview(**data)
    passed = result.score >= 7
    out_dir = stage_dir(Path(state["run_dir"]), 4, "code", code["attempt"])
    write_json(out_dir, "review", result.model_dump())
    return {
        "code": {
            **code,
            "status": "passed" if passed else "failed_needs_rework",
            "review": result.model_dump()
        }
    }