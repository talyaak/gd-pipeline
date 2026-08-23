import json
from datetime import datetime, timezone
from pathlib import Path

from config import OUTPUT_DIR


def new_run_dir(brief: str) -> Path:
    slug = "".join(c if c.isalnum() else "_" for c in brief.lower())[:40].strip("_")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(OUTPUT_DIR) / f"{slug}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def stage_dir(run_dir: Path, step_index: int, step_name: str, attempt: int) -> Path:
    path = run_dir / f"{step_index:02d}_{step_name}" / f"attempt_{attempt}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, name: str, data: dict) -> None:
    (path / f"{name}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_text(path: Path, name: str, text: str) -> None:
    (path / name).write_text(text, encoding="utf-8")
