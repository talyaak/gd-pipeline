"""Lightweight validation for generated HTML5 Phaser 3 game code.

Catches common LLM code-gen mistakes (undefined variables, external asset
references, missing structure) without an LLM call. Run before the code
review node to short-circuit obviously broken code and save tokens.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path


# Variable names that LLMs like to hallucinate instead of 'dt'
_BANNED_DT_NAMES = ("deltaTime", "elapsed", "deltaT", "elapsedTime")

# File extensions that indicate external asset loading
_ASSET_EXTENSIONS = re.compile(
    r"""(?:['"`])       # opening quote
    [^'"`]*             # path characters
    \.(?:png|jpe?g|gif|svg|webp|mp3|wav|ogg|m4a|flac|ttf|otf|woff2?)  # extension
    (?:['"`])           # closing quote""",
    re.VERBOSE | re.IGNORECASE,
)

# Phaser load calls that reference external files
_PHASER_LOAD = re.compile(
    r"this\.load\.(?:image|spritesheet|audio|atlas|multiatlas|bitmapFont|tilemapTiledJSON)\s*\(",
)


def check_html_game(html: str) -> list[str]:
    """Run sanity checks on generated game HTML.

    Returns a list of issue strings.  Empty list = all checks passed.
    """
    issues: list[str] = []

    # ── HTML structure ────────────────────────────────────────────────
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
        if re.search(rf"(?<![\"'`/])\b{bad}\b", js):
            issues.append(
                f"'{bad}' referenced — must be 'dt'. Will cause ReferenceError."
            )

    # ── External asset references (404 guarantee) ─────────────────────
    asset_matches = _ASSET_EXTENSIONS.findall(js)
    if asset_matches:
        files = ", ".join(m.strip("'\"` ") for m in asset_matches[:5])
        issues.append(
            f"External asset files referenced ({files}). "
            "These don't exist — use generateTexture() / Web Audio instead."
        )

    load_matches = _PHASER_LOAD.findall(js)
    if load_matches:
        issues.append(
            f"this.load.image/audio/etc. called {len(load_matches)} time(s). "
            "No external files exist — generate all textures procedurally."
        )

    # ── Node.js syntax check (if available) ───────────────────────────
    _run_node_syntax_check(js, issues)

    # ── Phaser structure checks ───────────────────────────────────────
    if "Phaser.Game" not in js and "new Phaser" not in js:
        issues.append("No Phaser.Game instantiation found.")

    if "Phaser.Scene" not in js:
        issues.append("No Phaser.Scene class found — need at least one scene.")

    if "update" not in js:
        issues.append("No update() method found in any scene.")

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
