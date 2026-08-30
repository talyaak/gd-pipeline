"""Deterministic P3.5 gate check - zero LLM involvement, on purpose.

This exists because three separate cycles satisfied the P3.5 "pipeline actually
produces a playable game" gate using prose-based self-assessment, and each one
found a different way to be technically defensible while being substantively
wrong: a mid-pipeline artifact mistaken for a completion, and (twice) genuine
evidence that was stale relative to the code actually being gated.

WHAT "SUCCESS" ACTUALLY MEANS, TRACED TO SOURCE (pipeline/cli.py's main()):
the real, load-bearing signal is pipeline_summary.json - a dict of every
stage's status, written UNCONDITIONALLY every run, pass or fail. The
top-level game.html is a SEPARATE, secondary artifact: cli.py writes it only
`if code.get("status") == "passed" and final_html`, which in normal graph
operation implies execution also passed on that attempt (the rework loop
feeds execution's own evidence back into codegen, so code doesn't reach
"passed" while execution still needs rework) - but that's an inference about
graph behavior, not a guarantee this script re-derives independently. So:
trust pipeline_summary.json's per-stage statuses as the primary fact:
game.html's existence is corroborating, not sufficient alone. A file in an
attempt_N/ or 0N_stage/ subfolder is mid-pipeline evidence and never counts,
regardless of what pipeline_summary.json says.

ALSO CHECKED: that the candidate run was actually GENERATED after the code
that produces it last changed. "Most recent run by file time" is not enough
on its own - an old passing run sitting untouched while pipeline/nodes/ or
pipeline/vendor/ get edited afterward is stale evidence in a new shape, the
same failure mode as citing an old run by hand, just automated instead of
manual. This script parses the run's own timestamp from its directory name
(the pipeline names runs `<genre>_<UTC-timestamp>Z>`) and requires it to be
newer than the latest commit touching those paths.

This script replaces "read the docs, use judgment" with a mechanical check
and, on failure, prints the recent output/ folder's actual contents so
whoever reads the output (agent or human) is oriented in real state rather
than a single cryptic pass/fail line.

Usage: python pipeline/gate_check.py
Exit 0 + writes .pipeline_gate_state.json only on a genuine, fresh pass.
Exit 1 on any failure, with the specific reason printed - never a partial
or "probably fine" state.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"
STATE_FILE = REPO_ROOT / ".pipeline_gate_state.json"

# Matches the pipeline's own run-naming convention, e.g. endless_runner_20260830T031640Z
RUN_TIMESTAMP_RE = re.compile(r"(\d{8}T\d{6}Z)$")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()


def _run_generated_at(run_dir: Path) -> datetime | None:
    m = RUN_TIMESTAMP_RE.search(run_dir.name)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def _last_relevant_code_change() -> datetime:
    iso = _git("log", "-1", "--format=%cI", "--", "pipeline/nodes", "pipeline/vendor")
    if not iso:
        # No commit has ever touched these paths - any run is fresh enough.
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(iso)


def _all_run_dirs_newest_first() -> list[Path]:
    if not OUTPUT_DIR.exists():
        return []
    return sorted((d for d in OUTPUT_DIR.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime, reverse=True)


def _print_output_folder_context(run_dirs: list[Path], limit: int = 8) -> None:
    # Retrieve-on-demand, not front-loaded: one line per run with a verdict
    # and the single stage that failed (if any) - enough to spot a repeating
    # pattern across runs without dumping every stage's status for all of
    # them into every failure message. Full detail for any specific run is
    # one command away, named explicitly, not pre-fetched speculatively.
    print("")
    print(f"Recent runs in {OUTPUT_DIR} (newest first, up to {limit} - for full detail on any")
    print(f"one, run: cat output/<run_name>/pipeline_summary.json):")
    for d in run_dirs[:limit]:
        summary_path = d / "pipeline_summary.json"
        has_top_level_html = (d / "game.html").exists()
        if not summary_path.exists():
            verdict = "IN-PROGRESS-OR-KILLED (no pipeline_summary.json)"
        else:
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                failed = {k: v for k, v in summary.items() if v != "passed"}
                if not failed:
                    verdict = "ALL-PASSED" if has_top_level_html else "PASSED-BUT-NO-TOP-LEVEL-HTML (inconsistent, worth a look)"
                else:
                    first_failed_stage = next(iter(failed))
                    verdict = f"FAILED at '{first_failed_stage}' ({failed[first_failed_stage]})"
            except json.JSONDecodeError:
                verdict = "UNREADABLE pipeline_summary.json"
        print(f"  {d.name}: {verdict}")


def main() -> int:
    run_dirs = _all_run_dirs_newest_first()
    if not run_dirs:
        print("FAIL: no output/ run directories exist at all. Run the pipeline first.")
        return 1

    run_dir = run_dirs[0]
    game_html = run_dir / "game.html"
    summary_path = run_dir / "pipeline_summary.json"

    if not summary_path.exists():
        print(f"FAIL: most recent run '{run_dir.name}' has no pipeline_summary.json at all -")
        print("      it may still be in progress, or was killed mid-run.")
        _print_output_folder_context(run_dirs)
        return 1

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FAIL: pipeline_summary.json in '{run_dir.name}' is not valid JSON: {e}")
        _print_output_folder_context(run_dirs)
        return 1

    # Primary source of truth: the per-stage statuses cli.py writes unconditionally.
    failed_stages = {k: v for k, v in summary.items() if v != "passed"}
    if failed_stages:
        print(f"FAIL: '{run_dir.name}' has failed stages per pipeline_summary.json: {failed_stages}")
        print("      This is the load-bearing check - a game.html existing (or not) doesn't override it.")
        _print_output_folder_context(run_dirs)
        return 1

    # Corroborating check, not a substitute for the above: the TOP-LEVEL file must
    # also exist. A file in attempt_N/ or 0N_stage/ never counts, no matter what
    # the summary says - if the summary claims all-passed but this file is missing,
    # something is inconsistent and that's itself worth failing loudly on.
    if not game_html.exists():
        print(f"FAIL: pipeline_summary.json for '{run_dir.name}' claims all stages passed, but the")
        print(f"      TOP-LEVEL game.html is missing (checked: {game_html}).")
        print("      This inconsistency is itself the finding - don't paper over it by trusting")
        print("      either signal alone. A file inside attempt_N/ or 0N_stage/ does not count.")
        _print_output_folder_context(run_dirs)
        return 1

    # Recency: the run must have been GENERATED after the code that produces it
    # last changed, not merely be the newest file lying around.
    generated_at = _run_generated_at(run_dir)
    last_code_change = _last_relevant_code_change()
    if generated_at is not None and generated_at < last_code_change:
        print(f"FAIL: '{run_dir.name}' passed, but it was generated at {generated_at.isoformat()},")
        print(f"      which is BEFORE the last commit touching pipeline/nodes/ or pipeline/vendor/")
        print(f"      ({last_code_change.isoformat()}). This run does not reflect current code -")
        print("      it's stale evidence, the same failure mode as citing an old run by hand.")
        print("      Run the pipeline again, fresh, on the current codebase.")
        _print_output_folder_context(run_dirs)
        return 1

    head = _git("rev-parse", "HEAD")
    state = {
        "commit_hash": head,
        "run_dir": run_dir.name,
        "run_generated_at": generated_at.isoformat() if generated_at else None,
        "last_relevant_code_change": last_code_change.isoformat(),
        "verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    print(f"PASS: '{run_dir.name}' has a top-level game.html, all stages passed, and the run")
    print(f"      postdates the last relevant code change ({last_code_change.isoformat()}).")
    print(f"      Gate stamped for commit {head[:12]} -> {STATE_FILE}")
    print("      This stamp is only valid for this exact commit. Any new commit")
    print("      invalidates it automatically - that's the point, not a bug.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
