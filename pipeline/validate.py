import re
import shutil
import subprocess
import tempfile
from pathlib import Path

BANNED_DELTA_TIME_NAMES = ["deltaTime", "elapsedTime", "deltaT", "elapsed"]

ASSET_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp", "svg", "mp3", "wav", "ogg", "m4a"]

ASSET_LOADER_CALLS = [
    "load.image",
    "load.audio",
    "load.spritesheet",
    "load.atlas",
    "load.bitmapFont",
    "load.tilemapTiledJSON",
]

# Patterns that indicate external network usage
EXTERNAL_SCRIPT_TAG = re.compile(r'<script\s+src\s*=\s*["\']https?://', re.IGNORECASE)
NETWORK_API_CALLS = [
    "fetch(",
    "XMLHttpRequest",
    "WebSocket(",
    "navigator.sendBeacon",
]


def _extract_script_contents(html: str) -> str:
    scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.DOTALL | re.IGNORECASE)
    return "\n".join(scripts)


def check_html_game(html: str) -> list[str]:
    """Static, deterministic checks. No LLM calls. Returns a list of issue strings (empty = clean)."""
    issues: list[str] = []
    script = _extract_script_contents(html)

    if not html.lstrip().lower().startswith("<!doctype html"):
        issues.append("File does not start with <!DOCTYPE html>")

    for name in BANNED_DELTA_TIME_NAMES:
        if re.search(rf"\b{re.escape(name)}\b", script):
            issues.append(f"Uses banned delta-time variable name '{name}' (must use 'dt')")

    for call in ASSET_LOADER_CALLS:
        if call in script:
            issues.append(f"Calls asset loader '{call}' — all textures/audio must be procedural")

    for ext in ASSET_EXTENSIONS:
        if re.search(rf"""['"][^'"]+\.{ext}['"]""", script, re.IGNORECASE):
            issues.append(f"References an external asset file (.{ext}) — all assets must be generated in-code")

    if "Phaser.Game" not in script:
        issues.append("Missing 'new Phaser.Game(...)' instantiation")

    if not re.search(r"\bupdate\s*\(", script):
        issues.append("No update() method found")

    # Check for external script tags (CDN references)
    if EXTERNAL_SCRIPT_TAG.search(html):
        issues.append("Contains external <script src=\"http...\"> tag — all code must be self-contained")

    # Check for network API calls
    for api in NETWORK_API_CALLS:
        if api in script:
            issues.append(f"Uses network API '{api}' — no external network access allowed")

    # Check for mraid.ready() calls - creative must not call mraid.ready() themselves
    if re.search(r'\.ready\(', script) or 'mraid.ready' in script:
        issues.append("Calls mraid.ready() — creative code must not call mraid.ready() themselves; gate gameplay on mraid.getState() !== 'loading' and mraid.isViewable()")
    # Check for muted-until-interaction audio policy
        # Audio must start muted and only unmute/resume after first user interaction
        # Check for AudioContext resume() calls
        resume_matches = list(re.finditer(r'(\b[\w.]+)\s*\.\s*resume\s*\(', script))
        for m in resume_matches:
            prefix = m.group(1)
            # Skip known non-audio resume calls
            if prefix in ('scene', 'this.scene', 'tweens', 'this.tweens', 'this.time', 'this.cache', 'this.textures', 'this.sound', 'this.game'):
                continue
            issues.append("Audio may start unmuted: AudioContext.resume() found. If this call is not guarded by user interaction (pointerdown, keyup, etc.), audio must start muted.")
            break
        # Check for audio element play() calls
        play_matches = list(re.finditer(r'(\b[\w.]+)\s*\.\s*play\s*\(', script))
        for m in play_matches:
            prefix = m.group(1)
            if prefix in ('this.sound', 'this.audio', 'HTMLAudioElement'):
                continue
            issues.append("Audio may start unmuted: HTMLAudioElement.play() found. If this call is not guarded by user interaction (pointerdown, keyup, etc.), audio must start muted.")
            break

    # Semantic validation requirements (must be present for browser execution to pass)
    # 1. Main gameplay scene must be named 'PlayScene' or contain 'play' for validation
    scene_class_match = re.search(r'class\s+(\w+)\s+extends\s+Phaser\.Scene', script)
    if scene_class_match:
        scene_constructor_match = re.search(rf'class\s+{scene_class_match.group(1)}\s+extends\s+Phaser\.Scene\s*\{{[^}}]*super\([\'"]([^\'"]+)[\'"]\)', script, re.DOTALL)
        if scene_constructor_match:
            scene_key = scene_constructor_match.group(1).lower()
            if 'play' not in scene_key and 'game' not in scene_key:
                issues.append(f"Main scene key '{scene_constructor_match.group(1)}' must include 'play' or 'game' for semantic validation (use 'PlayScene')")
    else:
        issues.append("No Phaser.Scene class found")
    
    # 2. Score registry initialization after window.__GAME__ = game
    if 'window.__GAME__' in script or 'window\\.__GAME__' in script:
        if 'game.registry.set' not in script and 'registry.set' not in script:
            issues.append("Missing game.registry.set('score', 0) after window.__GAME__ = game; — required for semantic validation")
    
    # 3. At least one of: score increment in registry in update() OR session time tracking on game instance
    # Semantic validation requires: sceneActiveAndGameplay AND (scoreIncreasing OR sessionTimeValid)
    has_score_increment = 'registry.inc' in script
    has_session_time = 'sessionTime' in script
    if 'update(' in script:
        if not has_score_increment and not has_session_time:
            issues.append("Missing both this.game.registry.inc('score', 1) and this.game.sessionTime tracking in update() — at least one is required for semantic validation to prove active gameplay/engagement")

    node_issues = _check_js_syntax(script)
    issues.extend(node_issues)

    return issues


class SyntaxCheckUnavailable(RuntimeError):
    """Raised when the JS syntax check could not run at all (missing/broken `node`).
    This must never be swallowed into an empty issue list — an unavailable check is
    not the same as a passed check, and letting it through as [] would let a game
    with a real syntax error masquerade as clean."""


def _check_js_syntax(script: str) -> list[str]:
    if not script.strip():
        return []
    node = shutil.which("node")
    if not node:
        raise SyntaxCheckUnavailable("`node` executable not found on PATH — cannot run JS syntax check")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(script)
        temp_path = f.name
    try:
        result = subprocess.run([node, "--check", temp_path], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return [f"JS syntax error (node --check): {result.stderr.strip()[:300]}"]
        return []
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise SyntaxCheckUnavailable(f"JS syntax check failed to run: {exc}") from exc
    finally:
        Path(temp_path).unlink(missing_ok=True)
