#!/usr/bin/env python3
"""
Reskin/parametrize layer for on-demand playable generation.

Given a brief + a harness manifest, substitutes parameter values into the
harness's .game.js and produces a reskinned game.js ready for the standard
build script. No LLM calls -- this is template filling, not code generation.

Usage:
    python -m pipeline.reskin briefs/match_3_brief.json
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_brief(brief: dict, manifest: dict) -> list[str]:
    """Validate brief values against manifest bounds. Returns list of errors (empty = valid)."""
    errors = []
    params = manifest.get("params", {})

    for key, spec in params.items():
        if key not in brief:
            errors.append(f"Missing required parameter: {key}")
            continue

        value = brief[key]
        vtype = spec.get("type")

        if vtype == "int":
            if not isinstance(value, int):
                errors.append(f"{key}: expected int, got {type(value).__name__}")
            else:
                if "min" in spec and value < spec["min"]:
                    errors.append(f"{key}: {value} < min {spec['min']}")
                if "max" in spec and value > spec["max"]:
                    errors.append(f"{key}: {value} > max {spec['max']}")

        elif vtype == "color_array":
            if not isinstance(value, list):
                errors.append(f"{key}: expected color array, got {type(value).__name__}")
            else:
                count = spec.get("count")
                if count and len(value) != count:
                    errors.append(f"{key}: expected {count} colors, got {len(value)}")
                for i, c in enumerate(value):
                    if isinstance(c, str):
                        if not re.match(r"^0x[0-9a-fA-F]{6}$", c):
                            errors.append(f"{key}[{i}]: invalid hex color format '{c}' (expected 0xRRGGBB)")
                    elif isinstance(c, int):
                        if c < 0 or c > 0xFFFFFF:
                            errors.append(f"{key}[{i}]: color value {c} out of range 0x000000-0xFFFFFF")
                    else:
                        errors.append(f"{key}[{i}]: expected hex string or int, got {type(c).__name__}")

        elif vtype == "string":
            if not isinstance(value, str):
                errors.append(f"{key}: expected string, got {type(value).__name__}")

        else:
            errors.append(f"{key}: unknown type '{vtype}' in manifest")

    # Check copy_slots
    copy_slots = manifest.get("copy_slots", [])
    for slot in copy_slots:
        if slot not in brief.get("copy", {}):
            errors.append(f"Missing required copy slot: copy.{slot}")

    # Check asset_slots (existence validated at build time)
    asset_slots = manifest.get("asset_slots", [])
    for slot in asset_slots:
        if slot not in brief:
            errors.append(f"Missing required asset slot: {slot}")

    return errors


def substitute_consts(source_js: str, params: dict[str, Any], copy: dict[str, str], assets: dict[str, str]) -> str:
    """
    Substitute const values in the harness .game.js file.

    Replaces lines like:
        const TARGET_SCORE = 1200;
        const COLORS = [0x33e6ff, ...];
        const START_MOVES = 20;

    With new values from the brief. Also handles string constants for copy/asset slots.
    """
    result = source_js

    # Substitute numeric/array params
    for key, value in params.items():
        if isinstance(value, list):
            # Format as JS array literal
            formatted = "[" + ", ".join(str(v) for v in value) + "]"
        elif isinstance(value, str):
            # String values need quotes
            formatted = f'"{value}"'
        else:
            formatted = str(value)

        # Match: const KEY = <anything>;
        # Use \g<1> syntax to avoid ambiguity with digits in formatted value
        pattern = rf"(const\s+{re.escape(key)}\s*=\s*)[^;]+(\s*;)"
        replacement = rf"\g<1>{formatted}\g<2>"
        new_result = re.sub(pattern, replacement, result)
        if new_result == result:
            # Also try with trailing comment
            pattern = rf"(const\s+{re.escape(key)}\s*=\s*)[^;]+(\s*;\s*//.*)?"
            replacement = rf"\g<1>{formatted}\g<2>"
            new_result = re.sub(pattern, replacement, result)
        result = new_result

    # Note: copy/asset slots are not consts in the .game.js -- they're used at HTML
    # build time (title in <title>, logo as asset reference). The reskin step only
    # substitutes gameplay params. The HTML build can read copy/asset from the brief.

    return result


def run_build_script(harness_name: str, title: str, src_game_js: str | None = None) -> tuple[bool, str]:
    """Run the standard harness build script. Returns (success, output/error)."""
    script_path = Path(__file__).parent.parent / "scripts" / "build_harness_html.sh"
    try:
        args = [str(script_path), harness_name, title]
        if src_game_js:
            args.append(src_game_js)
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
            check=False,
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def verify_with_playwright(html_path: Path) -> tuple[bool, str]:
    """
    Run Playwright execution validation on the built HTML.
    Returns (success, message).
    """
    try:
        # Import here to avoid dependency if not verifying
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from pipeline.execute import run_execution_report

        html = html_path.read_text()
        out_dir = Path(tempfile.mkdtemp())
        report = run_execution_report(html, out_dir)

        # Check all critical success criteria
        checks = [
            ("loaded", report.loaded),
            ("canvas_rendered", report.canvas_rendered),
            ("input_response_detected", report.input_response_detected),
            ("no_console_errors", len(report.console_errors) == 0),
        ]

        failures = [name for name, passed in checks if not passed]
        if failures:
            return False, f"Verification failed: {', '.join(failures)}. Console errors: {report.console_errors}"

        return True, f"Verification passed: loaded={report.loaded}, canvas={report.canvas_rendered}, input={report.input_response_detected}, engagement={report.engagement_duration_ms}ms"

    except Exception as e:
        return False, f"Verification error: {e}"


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="pipeline.reskin",
        description="Reskin a hand-built harness with brief parameters (no LLM calls)."
    )
    parser.add_argument("brief", help="Path to brief JSON file")
    parser.add_argument(
        "-o", "--output",
        help="Output directory for generated game.js (default: harness/<genre>_reskinned/)",
        default=None,
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Also run build_harness_html.sh to produce final HTML",
    )
    parser.add_argument(
        "--title",
        help="Title for HTML build (default: brief.copy.title or genre)",
        default=None,
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="After building HTML, run Playwright execution validation",
    )
    args = parser.parse_args()

    brief_path = Path(args.brief)
    if not brief_path.exists():
        print(f"Error: brief file not found: {brief_path}", file=sys.stderr)
        return 1

    brief = load_json(brief_path)
    genre = brief.get("genre")
    if not genre:
        print("Error: brief must contain 'genre' field", file=sys.stderr)
        return 1

    # Load manifest
    manifest_path = Path(__file__).parent.parent / "harness" / f"{genre}.manifest.json"
    if not manifest_path.exists():
        print(f"Error: manifest not found for genre '{genre}': {manifest_path}", file=sys.stderr)
        return 1

    manifest = load_json(manifest_path)
    if manifest.get("harness") != genre:
        print(f"Error: manifest harness field mismatch: expected '{genre}', got '{manifest.get('harness')}'", file=sys.stderr)
        return 1

    # Validate
    errors = validate_brief(brief, manifest)
    if errors:
        print("Validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    # Load harness .game.js
    harness_js_path = Path(__file__).parent.parent / "harness" / f"{genre}.game.js"
    if not harness_js_path.exists():
        print(f"Error: harness .game.js not found: {harness_js_path}", file=sys.stderr)
        return 1

    source_js = harness_js_path.read_text(encoding="utf-8")

    # Substitute
    params = {k: brief[k] for k in manifest.get("params", {}) if k in brief}
    copy = brief.get("copy", {})
    assets = {k: brief[k] for k in manifest.get("asset_slots", []) if k in brief}

    reskinned_js = substitute_consts(source_js, params, copy, assets)

    # Determine output path
    if args.output:
        out_dir = Path(args.output)
    else:
        out_dir = Path(__file__).parent.parent / "harness" / f"{genre}_reskinned"

    out_dir.mkdir(parents=True, exist_ok=True)
    out_js_path = out_dir / f"{genre}.game.js"
    out_js_path.write_text(reskinned_js, encoding="utf-8")

    print(f"Reskinned game.js written to: {out_js_path}")

    # Optionally build HTML
    html_path = None
    if args.build:
        title = args.title or copy.get("title") or f"{genre.replace('_', ' ').title()} - Reskin"
        print(f"Building HTML with title: {title}")
        # build_harness_html.sh always writes to harness/<NAME>.html -- passing
        # the bare genre here would silently overwrite the hand-built, already
        # Playwright-verified master harness (harness/<genre>.html) with this
        # one brief's values. Use a distinct output name so reskins never touch
        # the master file, no matter how many briefs get built for this genre.
        output_name = f"{genre}_reskinned/{brief_path.stem}"
        (Path(__file__).parent.parent / "harness" / f"{genre}_reskinned").mkdir(parents=True, exist_ok=True)
        success, output = run_build_script(output_name, title, str(out_js_path))
        if success:
            html_path = Path(__file__).parent.parent / "harness" / f"{output_name}.html"
            print(f"HTML built: {html_path}")
            print(output.strip())
        else:
            print(f"Build failed: {output}", file=sys.stderr)
            return 1

    # Optionally verify with Playwright
    if args.verify:
        if not html_path:
            print("Error: --verify requires --build to produce HTML first", file=sys.stderr)
            return 1
        print("Running Playwright verification...")
        success, message = verify_with_playwright(html_path)
        print(message)
        if not success:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())