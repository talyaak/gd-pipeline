from pathlib import Path
import gzip

from pipeline.execute import run_execution_report
from pipeline.output import stage_dir, write_json
from pipeline.schemas import RunState
from pipeline.validate import check_html_game

# Size gate: gzipped HTML must be under 500KB
MAX_GZIP_SIZE_KB = 500

# Timing validation thresholds
TTFI_TOLERANCE_MS = 1000  # Allow 1s buffer over target
MIN_COMPLETION_RATE = 0.5  # At least 50% of target session completed
MIN_ENGAGEMENT_FRACTION = 0.3  # At least 30% of target session in active play


def _check_timing_metrics(report, spec_artifact: dict) -> list[str]:
    """Validate execution timing metrics against spec targets.
    
    Returns list of violation messages (empty = all metrics pass).
    """
    violations = []
    
    # Extract timing targets from spec (with defaults)
    target_session_seconds = spec_artifact.get("target_session_seconds", 30)
    time_to_first_interaction_target_seconds = spec_artifact.get("time_to_first_interaction_target_seconds", 4)
    
    target_session_ms = target_session_seconds * 1000
    tti_target_ms = time_to_first_interaction_target_seconds * 1000
    
    # 1. Time-to-first-interaction check
    if report.time_to_first_interaction_ms is not None:
        tti_ms = report.time_to_first_interaction_ms
        max_allowed_tti = tti_target_ms + TTFI_TOLERANCE_MS
        if tti_ms > max_allowed_tti:
            violations.append(
                f"Time-to-first-interaction ({tti_ms}ms) exceeds target "
                f"({tti_target_ms}ms) + tolerance ({TTFI_TOLERANCE_MS}ms) = {max_allowed_tti}ms"
            )
    else:
        violations.append("Time-to-first-interaction not measured")
    
    # 2. Completion rate check
    if report.completion_rate is not None:
        if report.completion_rate < MIN_COMPLETION_RATE:
            violations.append(
                f"Completion rate ({report.completion_rate:.2f}) below minimum ({MIN_COMPLETION_RATE})"
            )
    else:
        violations.append("Completion rate not measured")
    
    # 3. Engagement duration check
    if report.engagement_duration_ms is not None:
        min_engagement_ms = target_session_ms * MIN_ENGAGEMENT_FRACTION
        if report.engagement_duration_ms < min_engagement_ms:
            violations.append(
                f"Engagement duration ({report.engagement_duration_ms}ms) below minimum "
                f"({MIN_ENGAGEMENT_FRACTION * 100:.0f}% of target session = {min_engagement_ms}ms)"
            )
    else:
        violations.append("Engagement duration not measured")
    
    return violations


def validate_execute(state: RunState) -> dict:
    code = state.get("code", {})
    attempt = code.get("attempt", 0)
    html = code.get("artifact", {}).get("html", "")
    
    # Get spec artifact for timing targets
    spec_artifact = state.get("spec", {}).get("artifact") or {}

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
    
    # Additional timing metric validation (only if basic runtime passed)
    timing_violations = []
    if runtime_ok:
        timing_violations = _check_timing_metrics(report, spec_artifact)
        if timing_violations:
            runtime_ok = False

    all_errors = []
    if not runtime_ok:
        if report.console_errors:
            all_errors.extend(report.console_errors)
        if not report.canvas_rendered:
            all_errors.append("canvas did not render")
        if not report.input_response_detected:
            all_errors.append("no input response detected")
        if not report.loaded:
            all_errors.append("page failed to load")
        all_errors.extend(timing_violations)

    result = {
        "status": "passed" if runtime_ok else "failed_needs_rework",
        "attempt": attempt,
        "artifact": report.model_dump(),
        "review": None,
        "error": "; ".join(all_errors) if all_errors else None,
    }
    write_json(out_dir, "execution", result)
    return {"execution": result}