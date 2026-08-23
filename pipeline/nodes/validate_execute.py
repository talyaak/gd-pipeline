from pathlib import Path

from pipeline.execute import run_execution_report
from pipeline.output import stage_dir, write_json
from pipeline.schemas import RunState
from pipeline.validate import check_html_game


def validate_execute(state: RunState) -> dict:
    code = state["code"]
    attempt = code["attempt"]
    html = code["artifact"]["html"]

    out_dir = stage_dir(Path(state["run_dir"]), 5, "execution", attempt)

    static_issues = check_html_game(html)
    if static_issues:
        result = {
            "status": "failed_needs_rework",
            "attempt": attempt,
            "artifact": None,
            "review": None,
            "error": "; ".join(static_issues),
        }
        write_json(out_dir, "execution", result)
        return {"execution": result}

    report = run_execution_report(html, out_dir)

    runtime_ok = report.loaded and not report.console_errors and report.canvas_rendered
    result = {
        "status": "passed" if runtime_ok else "failed_needs_rework",
        "attempt": attempt,
        "artifact": report.model_dump(),
        "review": None,
        "error": None if runtime_ok else ("; ".join(report.console_errors) or "canvas did not render"),
    }
    write_json(out_dir, "execution", result)
    return {"execution": result}
