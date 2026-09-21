# Handling Self-Contained HTML in Validation Harness

## Problem

The validation harness (`pipeline/execute.py`) injects vendored Phaser + Juice into ALL HTML it tests. However, hand-authored harness games (built via `scripts/build_harness_html.sh`) are already self-contained — they bundle Phaser + Juice + game code into a single `<script>` block.

Injecting vendor scripts into self-contained HTML causes:
1. **Duplicate class declarations**: `"Identifier 'ScreenShake' already declared"` console errors
2. **Broken `window.__GAME__` detection**: The second Phaser.Game instantiation overwrites the first, losing the game instance with the state
3. **Semantic validation failure**: `game.state` never reads `'playing'`

## Detection Heuristic

Add a function to detect self-contained HTML by checking for actual bundled exports (not mere references):

```python
def _has_vendor_scripts(html: str) -> bool:
    """Check if HTML already contains bundled vendor scripts (Phaser/Juice).
    Self-contained harness games include Phaser + Juice + game code in one <script> block.
    Heuristics: look for actual bundled code exports/definitions, not mere references.
    """
    # Harness games bundle the full Juice toolkit which exports: window.Juice = { ... }
    # They also define Juice classes like ScreenShake in the global scope.
    # The Phaser minified bundle is ~1MB and starts with a UMD wrapper.
    # Fixtures only REFERENCE Phaser/Juice without including them.
    return any(marker in html for marker in (
        "window.Juice = {",    # Actual Juice namespace export
        "class ScreenShake",   # Juice class definition (bundled)
        "window.__GAME__ = this.game",  # Harness-specific pattern
    ))
```

## Usage in Execution Harness

```python
def run_execution_report(html: str, out_dir: Path) -> ExecutionReport:
    out_dir.mkdir(parents=True, exist_ok=True)

    # Skip vendor injection for self-contained HTML (harness games)
    needs_vendor = not _has_vendor_scripts(html)

    if needs_vendor:
        # Inject vendored Phaser...
        if "</head>" in html:
            html = html.replace("</head>", f"<script>{PHASER_JS}</script></head>")
        else:
            html = html.replace("<body>", f"<body><script>{PHASER_JS}</script>")

        # Inject MRAID wrapper, particle.js, ui.js, art.js, juice.js...
        # (only if needs_vendor is True)
```

## Key Insight

The detection must look for **actual bundled exports/definitions** (`window.Juice = {`, `class ScreenShake`), not mere references (`Phaser.Game`, `window.Juice`). Fixtures and generated games often reference these without including them.

## Bug Fix: False Positives from Comments/Strings (2026-09-12)

**Bug**: Simple substring matching on full HTML caused false positives when markers appeared in:
- JavaScript comments (`// window.Juice = { ... }`)
- String literals (`"class ScreenShake"`)
- Template literals

A comment block containing two of the three markers would incorrectly return `True` even though no actual vendor code was bundled.

**Fix**: Strip JS comments (`//` and `/* */`) and string literals (single/double quotes, template literals) from `<script>` blocks before marker matching:

```python
def _has_vendor_scripts(html: str) -> bool:
    # Extract script content and strip JS comments (// and /* */) to avoid
    # false positives from markers appearing in comments or string literals.
    import re
    script_blocks = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    if not script_blocks:
        return False
    combined_script = "\n".join(script_blocks)
    # Remove single-line comments (// ...)
    combined_script = re.sub(r'//.*$', '', combined_script, flags=re.MULTILINE)
    # Remove multi-line comments (/* ... */)
    combined_script = re.sub(r'/\*.*?\*/', '', combined_script, flags=re.DOTALL)
    # Also remove string literals to be extra safe (single/double quotes, template literals)
    combined_script = re.sub(r'`[^`]*`', '', combined_script)
    combined_script = re.sub(r'"(?:[^"\\]|\\.)*"', '', combined_script)
    combined_script = re.sub(r"'(?:[^'\\]|\\.)*'", '', combined_script)

    # Count how many markers appear in the cleaned script content
    markers = (
        "window.Juice = {",    # Actual Juice namespace export
        "class ScreenShake",   # Juice class definition (bundled)
        "window.__GAME__ = this.game",  # Harness-specific pattern
    )
    match_count = sum(1 for marker in markers if marker in combined_script)
    # Require at least 2 of 3 markers to avoid single-marker false positives
    # (e.g., a comment containing "class ScreenShake" alone)
    return match_count >= 2
```

**Regression test added**: `tests/test_execute.py::test_has_vendor_scripts_rejects_two_markers_in_comment` - verifies two markers in a comment block no longer trigger false positive.

## Testing

Verify both paths work:
1. **Self-contained harness games** (match_3.html, ball_sort.html, etc.) — skip injection, semantic validation passes
2. **Generated/fixture games** (known_good_game.html, etc.) — inject vendor, validation passes

Run: `bash scripts/run_tests_compact.sh tests/test_execute.py tests/test_validate_execute.py`