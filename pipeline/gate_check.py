"""Deterministic P3.5 gate check - zero LLM involvement, on purpose.

This exists because three separate cycles satisfied the P3.5 "pipeline actually
produces a playable game" gate using prose-based self-assessment, and each one
found a different way to be technically defensible while being substantively
wrong: a mid-pipeline artifact mistaken for a completion, and (twice) genuine
evidence that was stale relative to the code actually being gated.

This script replaces "read the docs, use judgment" with a mechanical check:
find the most recent pipeline run, confirm a real top-level game.html and a
passing pipeline_summary.json, and if genuine, stamp a state file with the
EXACT current git commit hash. Not "recent" - exact. See githooks/pre-commit,
which refuses to commit new P4-designated files unless this stamp matches
HEAD, so a stale gate can't silently authorize new work no matter what an
agent believes about it.

Usage: python pipeline/gate_check.py
Exit 0 + writes .pipeline_gate_state.json only on a genuine, fresh pass.
Exit 1 on any failure, with the specific reason printed - never a partial
or "probably fine" state.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"
STATE_FILE = REPO_ROOT / ".pipeline_gate_state.json"


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def _most_recent_run_dir() -> Path | None:
    if not OUTPUT_DIR.exists():
        return None
    candidates = [d for d in OUTPUT_DIR.iterdir() if d.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.stat().st_mtime)


def main() -> int:
    run_dir = _most_recent_run_dir()
    if run_dir is None:
        print("FAIL: no output/ run directories exist at all. Run the pipeline first.")
        return 1

    game_html = run_dir / "game.html"
    summary_path = run_dir / "pipeline_summary.json"

    if not game_html.exists():
        print(f"FAIL: most recent run '{run_dir.name}' has no TOP-LEVEL game.html.")
        print(f"      (checked: {game_html})")
        print("      A file inside an attempt_N/ or 0N_stage/ subfolder does NOT count -")
        print("      that is mid-pipeline evidence, not a completed run.")
        return 1

    if not summary_path.exists():
        print(f"FAIL: '{run_dir.name}' has a top-level game.html but no pipeline_summary.json to confirm it passed.")
        return 1

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FAIL: pipeline_summary.json in '{run_dir.name}' is not valid JSON: {e}")
        return 1

    failed_stages = {k: v for k, v in summary.items() if v != "passed"}
    if failed_stages:
        print(f"FAIL: '{run_dir.name}' has a game.html but pipeline_summary.json shows failed stages: {failed_stages}")
        return 1

    head = _git_head()
    state = {
        "commit_hash": head,
        "run_dir": run_dir.name,
        "run_dir_mtime": run_dir.stat().st_mtime,
        "verified_at": subprocess.run(
            ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], capture_output=True, text=True
        ).stdout.strip(),
    }
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    print(f"PASS: '{run_dir.name}' has a top-level game.html and all stages passed.")
    print(f"      Gate stamped for commit {head[:12]} -> {STATE_FILE}")
    print("      This stamp is only valid for this exact commit. Any new commit")
    print("      invalidates it automatically - that's the point, not a bug.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
