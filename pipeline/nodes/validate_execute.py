from pathlib import Path
import gzip

from pipeline.execute import run_execution_report
from pipeline.output import stage_dir, write_json
from pipeline.schemas import RunState
from pipeline.validate import check_html_game

# Size gate: gzipped HTML must be under 500KB
MAX_GZIP_SIZE_KB = 500


def validate_execute(state: RunState) -> dict:
    code = state.get("code", {})
    attempt = code.get("attempt", 0)
    html = code.get("artifact", {}).get("html", "")

    out_dir = stage_dir(Path(state.get("run_dir", "")), 5, "execution", attempt)

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

    # Size gate: check gzipped HTML size
    gzipped_html = gzip.compress(html.encode("utf-8"))
    gzip_size_kb = len(gzipped_html) / 1024
    if gzip_size_kb > MAX_GZIP_SIZE_KB:
        result = {
            "status": "failed_needs_rework",
            "attempt": attempt,
            "artifact": None,
            "review": None,
            "error": f"Gzipped HTML size ({gzip_size_kb:.1f} KB) exceeds limit ({MAX_GZIP_SIZE_KB} KB)",
        }
        write_json(out_dir, "execution", result)
        return {"execution": result}

    report = run_execution_report(html, out_dir)

    runtime_ok = (
        report.loaded
        and not report.console_errors
        and report.canvas_rendered
        and report.input_response_detected
    )
    result = {
        "status": "passed" if runtime_ok else "failed_needs_rework",
        "attempt": attempt,
        "artifact": report.model_dump(),
        "review": None,
        "error": None if runtime_ok else ("; ".join(report.console_errors) or "canvas did not render"),
    }
    write_json(out_dir, "execution", result)
    return {"execution": result}