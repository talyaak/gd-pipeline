#!/usr/bin/env python3
"""Test reskin pipeline end-to-end with Playwright verification for remaining genres."""
import json
import tempfile
from pathlib import Path

import pytest

from pipeline.execute import run_execution_report
from pipeline.reskin import (
    load_json,
    validate_brief,
    substitute_consts,
    inject_mraid_gating,
    run_build_script,
    verify_with_playwright,
)

HARNESS_DIR = Path(__file__).parent.parent / "harness"
BRIEFS_DIR = Path(__file__).parent.parent / "briefs"


def run_reskin_test(genre: str, test_name: str):
    """Helper to run reskin test for a genre."""
    brief_path = BRIEFS_DIR / f"{genre}_brief.json"
    assert brief_path.exists(), f"Brief not found: {brief_path}"

    brief = load_json(brief_path)
    assert brief["genre"] == genre

    manifest_path = HARNESS_DIR / f"{genre}.manifest.json"
    manifest = load_json(manifest_path)

    # Validate brief
    errors = validate_brief(brief, manifest)
    assert not errors, f"Validation errors: {errors}"

    # Load harness .game.js
    harness_js_path = HARNESS_DIR / f"{genre}.game.js"
    source_js = harness_js_path.read_text(encoding="utf-8")

    # Substitute params
    params = {k: brief[k] for k in manifest.get("params", {}) if k in brief}
    copy = brief.get("copy", {})
    assets = {k: brief[k] for k in manifest.get("asset_slots", []) if k in brief}

    reskinned_js, warnings = substitute_consts(source_js, params, copy, assets)
    # Fail if any param failed to match (failed_noop)
    assert not warnings, f"Substitution failed_noop: {warnings}"

    reskinned_js = inject_mraid_gating(reskinned_js)

    # Build HTML
    output_name = f"{genre}_reskinned/{test_name}"
    out_dir = HARNESS_DIR / f"{genre}_reskinned"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_js_path = out_dir / f"{genre}.game.js"
    out_js_path.write_text(reskinned_js, encoding="utf-8")

    title = copy.get("title") or f"{genre.replace('_', ' ').title()} - Reskin"
    success, output = run_build_script(output_name, title, str(out_js_path), "true")
    assert success, f"Build failed: {output}"

    html_path = HARNESS_DIR / f"{output_name}.html"
    assert html_path.exists(), f"HTML not built: {html_path}"

    # Verify with Playwright
    success, message = verify_with_playwright(html_path)
    assert success, f"Playwright verification failed: {message}"

    print(message)


@pytest.mark.slow
def test_reskin_ball_sort(tmp_path):
    run_reskin_test("ball_sort", "test_ball_sort")


@pytest.mark.slow
def test_reskin_bullet_hell_shmup(tmp_path):
    run_reskin_test("bullet_hell_shmup", "test_bullet_hell_shmup")


@pytest.mark.slow
def test_reskin_pull_the_pin(tmp_path):
    run_reskin_test("pull_the_pin", "test_pull_the_pin")


@pytest.mark.slow
def test_reskin_stack_tower(tmp_path):
    run_reskin_test("stack_tower", "test_stack_tower")


@pytest.mark.slow
def test_reskin_tower_defense(tmp_path):
    run_reskin_test("tower_defense", "test_tower_defense")


@pytest.mark.slow
def test_reskin_farm_idle(tmp_path):
    run_reskin_test("farm_idle", "test_farm_idle")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])