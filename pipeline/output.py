"""Output management for the game design pipeline.

Provides a run-scoped output directory where each step saves its artifacts
into attempt-indexed subfolders.

    output/<genre>_<timestamp>/
        01_genre_research/
            analysis.json
        02_gdd/
            attempt_1/
                gdd.json
                review.json
            attempt_2/
                ...
            gdd_for_review.json        ← HITL convenience copy
        03_impl_spec/
            attempt_1/
                impl_spec.json
                review.json
            ...
        summary.json                   ← final combined result
"""

import json
from datetime import datetime, timezone
from pathlib import Path

_project_root: Path = Path(__file__).resolve().parent.parent
_run_dir: Path | None = None


def init_run(genre: str) -> Path:
    """Create and return the output directory for this pipeline run."""
    global _run_dir
    slug = genre.lower().replace(" ", "_")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    _run_dir = _project_root / "output" / f"{slug}_{ts}"
    _run_dir.mkdir(parents=True, exist_ok=True)
    return _run_dir


def init_resume(run_path: str | Path) -> Path:
    """Use an existing output directory for resuming a pipeline run."""
    global _run_dir
    path = Path(run_path)
    if not path.is_absolute():
        path = _project_root / path
    if not path.is_dir():
        raise FileNotFoundError(f"Resume path does not exist: {path}")
    _run_dir = path.resolve()
    return _run_dir


def save(
    step: str,
    filename: str,
    data: dict,
    *,
    attempt: int | None = None,
) -> Path:
    """Save a JSON artifact and return its path.

    Args:
        step: Folder name, e.g. "01_genre_research".
        filename: File name, e.g. "analysis.json".
        data: Serializable dict.
        attempt: If given, saves into attempt_N subfolder.
    """
    assert _run_dir is not None, "Call init_run() before saving."
    target = _run_dir / step
    if attempt is not None:
        target = target / f"attempt_{attempt}"
    target.mkdir(parents=True, exist_ok=True)
    path = target / filename
    path.write_text(json.dumps(data, indent=2, default=str))
    return path


def save_text(
    step: str,
    filename: str,
    text: str,
    *,
    attempt: int | None = None,
) -> Path:
    """Save a raw text file (e.g. .html) and return its path."""
    assert _run_dir is not None, "Call init_run() before saving."
    target = _run_dir / step
    if attempt is not None:
        target = target / f"attempt_{attempt}"
    target.mkdir(parents=True, exist_ok=True)
    path = target / filename
    path.write_text(text)
    return path


def rel(path: Path) -> str:
    """Return path relative to the project root for clean display."""
    try:
        return str(path.relative_to(_project_root))
    except ValueError:
        return str(path)


def run_dir() -> Path:
    """Return the current run's output directory."""
    assert _run_dir is not None, "Call init_run() first."
    return _run_dir


def save_pipeline_summary(
    *,
    title: str,
    one_liner: str,
    gdd_score: int | None,
    gdd_passed: bool | None,
    gdd_issues: list[str] | None,
    impl_spec_score: int | None,
    impl_spec_passed: bool | None,
    impl_spec_issues: list[str] | None,
    code_score: int | None,
    code_passed: bool | None,
    code_issues: list[str] | None,
) -> Path:
    """Save a human-readable pipeline summary as markdown."""
    assert _run_dir is not None, "Call init_run() first."
    path = _run_dir / "pipeline_summary.md"

    def fmt_issues(issues: list[str] | None) -> str:
        if not issues:
            return "_None_"
        return "\n".join(f"- {i}" for i in issues[:10]) + (
            f"\n- ... and {len(issues) - 10} more" if len(issues) > 10 else ""
        )

    md = f"""# Pipeline Summary: {title}

{one_liner}

## Scores

| Stage | Score | Status |
|-------|-------|--------|
| GDD | {gdd_score or '-'}/10 | {'PASSED' if gdd_passed else 'needs work'} |
| Impl Spec | {impl_spec_score or '-'}/10 | {'PASSED' if impl_spec_passed else 'needs work'} |
| Code | {code_score or '-'}/10 | {'PASSED' if code_passed else 'needs work'} |

## Key Blockers

### GDD
{fmt_issues(gdd_issues)}

### Impl Spec
{fmt_issues(impl_spec_issues)}

### Code
{fmt_issues(code_issues)}

---
Artifacts: {_run_dir.name}/
"""
    path.write_text(md, encoding="utf-8")
    return path
