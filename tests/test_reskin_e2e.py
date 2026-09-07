#!/usr/bin/env python3
"""Test reskin pipeline end-to-end with Playwright verification."""
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


def test_reskin_match_3(tmp_path):
    """Test reskin pipeline for match_3 genre end-to-end."""
    brief_path = BRIEFS_DIR / "match_3_brief.json"
    assert brief_path.exists(), f"Brief not found: {brief_path}"

    brief = load_json(brief_path)
    genre = brief["genre"]

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
    output_name = f"{genre}_reskinned/test_match_3"
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


def test_reskin_endless_runner(tmp_path):
    """Test reskin pipeline for endless_runner genre end-to-end."""
    brief_path = BRIEFS_DIR / "endless_runner_brief.json"
    assert brief_path.exists(), f"Brief not found: {brief_path}"

    brief = load_json(brief_path)
    genre = brief["genre"]

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
    output_name = f"{genre}_reskinned/test_endless_runner"
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


def test_reskin_idle_clicker(tmp_path):
    """Test reskin pipeline for idle_clicker genre end-to-end."""
    brief_path = BRIEFS_DIR / "idle_clicker_brief.json"
    assert brief_path.exists(), f"Brief not found: {brief_path}"

    brief = load_json(brief_path)
    genre = brief["genre"]

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
    output_name = f"{genre}_reskinned/test_idle_clicker"
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


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])