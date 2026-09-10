#!/usr/bin/env python3
"""CTA tests for farm_idle harness."""
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
)

HARNESS_DIR = Path(__file__).parent.parent / "harness"
BRIEFS_DIR = Path(__file__).parent.parent / "briefs"


def _build_farm_idle_html(brief_overrides: dict = None) -> str:
    """Build a farm_idle HTML with given brief overrides."""
    brief_path = BRIEFS_DIR / "farm_idle_brief.json"
    brief = load_json(brief_path)

    if brief_overrides:
        brief.update(brief_overrides)

    manifest_path = HARNESS_DIR / "farm_idle.manifest.json"
    manifest = load_json(manifest_path)

    # Validate brief
    errors = validate_brief(brief, manifest)
    assert not errors, f"Validation errors: {errors}"

    # Load harness .game.js
    harness_js_path = HARNESS_DIR / "farm_idle.game.js"
    source_js = harness_js_path.read_text(encoding="utf-8")

    # Substitute params
    params = {k: brief[k] for k in manifest.get("params", {}) if k in brief}
    copy = brief.get("copy", {})
    assets = {k: brief[k] for k in manifest.get("asset_slots", []) if k in brief}

    reskinned_js, warnings = substitute_consts(source_js, params, copy, assets)
    assert not warnings, f"Substitution failed_noop: {warnings}"

    reskinned_js = inject_mraid_gating(reskinned_js)

    # Build HTML
    import tempfile as tmp
    out_dir = Path(tmp.mkdtemp()) / "farm_idle_reskinned"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_js_path = out_dir / "farm_idle.game.js"
    out_js_path.write_text(reskinned_js, encoding="utf-8")

    title = copy.get("title") or "farm_idle - Reskin"
    success, output = run_build_script("farm_idle_reskinned/test_cta", title, str(out_js_path), "true")
    assert success, f"Build failed: {output}"

    html_path = HARNESS_DIR / "farm_idle_reskinned" / "test_cta.html"
    assert html_path.exists(), f"HTML not built: {html_path}"

    return html_path.read_text()


@pytest.mark.slow
def test_cta_disabled_by_default_renders_no_cta(tmp_path):
    """CTA_ENABLED=0 should render no CTA button."""
    html = _build_farm_idle_html({"CTA_ENABLED": 0})
    report = run_execution_report(html, tmp_path)

    assert report.loaded is True
    assert report.cta_exists is False
    assert report.cta_clicked is False
    assert report.cta_action_called is False


@pytest.mark.slow
def test_cta_enabled_passes_runtime_validation(tmp_path):
    """CTA_ENABLED=1 should pass runtime CTA validation (exists, clickable, action fires)."""
    html = _build_farm_idle_html({"CTA_ENABLED": 1})
    report = run_execution_report(html, tmp_path)

    assert report.loaded is True
    assert report.cta_exists is True
    assert report.cta_clicked is True
    assert report.cta_action_called is True
    assert not any("CTA validation" in e for e in report.console_errors)