"""Lightweight validation for generated HTML5 game code.

Catches common GPT-4o code-gen mistakes (undefined variables, missing
structure) without an LLM call. Run before the code review node to
short-circuit obviously broken code and save tokens.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path


# Variable names that GPT-4o likes to hallucinate instead of 'dt'
_BANNED_DT_NAMES = ("deltaTime", "elapsed", "deltaT", "elapsedTime")


def check_html_game(html: str) -> list[str]:
    """Run sanity checks on generated game HTML.

    Returns a list of issue strings.  Empty list = all checks passed.
    """
    issues: list[str] = []

    # ── HTML structure ────────────────────────────────────────────────
    if "<canvas" not in html:
        issues.append("Missing <canvas> element.")
    if "<script" not in html:
        issues.append("Missing <script> tag — no game code.")
        return issues

    # ── Extract JS ────────────────────────────────────────────────────
    js_blocks = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    js = "\n".join(js_blocks)
    if not js.strip():
        issues.append("Empty <script> — no game code.")
        return issues

    # ── Banned delta-time variable names ──────────────────────────────
    for bad in _BANNED_DT_NAMES:
        # Match word boundary, skip occurrences inside string literals
        if re.search(rf"(?<![\"'`/])\b{bad}\b", js):
            issues.append(
                f"'{bad}' referenced — must be 'dt'. Will cause ReferenceError."
            )

    # ── Node.js syntax check (if available) ───────────────────────────
    _run_node_syntax_check(js, issues)

    # ── Required game-loop structure ──────────────────────────────────
    if "requestAnimationFrame" not in js:
        issues.append("No requestAnimationFrame — missing game loop.")

    defined = set(re.findall(r"function\s+(\w+)\s*\(", js))

    if not defined & {"update", "gameLoop"}:
        issues.append("No update() or gameLoop() function defined.")
    if not defined & {"render", "draw"}:
        issues.append("No render() or draw() function defined.")

    return issues


def _run_node_syntax_check(js: str, issues: list[str]) -> None:
    """If Node.js is available, syntax-check the extracted JS."""
    node = shutil.which("node")
    if not node:
        return

    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(
            suffix=".js", mode="w", delete=False, encoding="utf-8"
        )
        tmp.write(js)
        tmp.close()

        result = subprocess.run(
            [node, "--check", tmp.name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            for line in result.stderr.strip().splitlines():
                if "Error" in line:
                    issues.append(f"JS syntax error: {line.strip()}")
                    break
    except (subprocess.TimeoutExpired, OSError):
        pass  # Node unavailable or timed out — skip
    finally:
        if tmp:
            Path(tmp.name).unlink(missing_ok=True)
