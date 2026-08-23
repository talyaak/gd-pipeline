import re
from pathlib import Path

from config import CODEGEN_MAX_TOKENS
from pipeline.llm import get_generation_llm
from pipeline.output import stage_dir, write_text
from pipeline.schemas import RunState

PROMPT = """You are a game programmer. Write ONE complete, self-contained HTML file that \
implements the game described below in Phaser 3.

Game Design Document:
{gdd}

Implementation Spec:
{spec}

Hard requirements:
- Output a single HTML file starting with <!DOCTYPE html>. Nothing before it, nothing \
after the closing </html> tag — no markdown fences, no commentary.
- Phaser 3 is PRELOADED as a global `Phaser` variable. Do NOT include any <script src="..."> tags for Phaser or any other external library. Write only your game code.
- Generate ALL textures procedurally at runtime via graphics.generateTexture(). Never call \
this.load.image, this.load.audio, this.load.spritesheet, or reference any image/audio file \
by path or extension (.png, .jpg, .mp3, .wav, etc.) anywhere in the code.
- Use the Web Audio API directly (new AudioContext(), oscillators) for any sound. No audio \
files.
- The delta-time variable in update(time, delta) must be named exactly 'dt' (e.g. \
`const dt = delta / 1000;`). Never use 'deltaTime', 'elapsed', or 'elapsedTime'.
- Implement a Phaser.Game with at least one Phaser.Scene that has create() and update() \
methods, and make the described controls and win/lose condition actually work.
- Declare every class before it is referenced (e.g. before it appears in a `scene: [...]` \
array), to avoid ReferenceError: Cannot access '<Class>' before initialization.
- Expose the Phaser.Game instance as `window.__GAME__` immediately after creation for \
semantic validation (e.g. `window.__GAME__ = game;`).
"""

REWORK_PROMPT = PROMPT + """

Your previous attempt failed. Here is the real evidence of what went wrong — fix these \
specific problems, don't just rewrite from scratch:

Static validation issues:
{static_issues}

Browser execution evidence:
- Loaded without crashing: {loaded}
- Console/runtime errors: {console_errors}
- Canvas rendered: {canvas_rendered}
- Input produced an observable change: {input_response}

Code review feedback (only relevant if execution evidence above is clean):
{review_issues}

Previous attempt's code, for reference:
{previous_html}
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:html)?\s*\n", "", text)
    text = re.sub(r"\n```\s*$", "", text)
    return text.strip()


def codegen(state: RunState) -> dict:
    gdd = state["design"]["artifact"]
    impl_spec = state["spec"]["artifact"]
    prior_code = state.get("code") or {}
    prior_execution = state.get("execution") or {}
    attempt = prior_code.get("attempt", 0) + 1

    llm = get_generation_llm(temperature=0.3, max_tokens=CODEGEN_MAX_TOKENS)

    if attempt == 1:
        prompt = PROMPT.format(gdd=gdd, spec=impl_spec)
    else:
        exec_artifact = prior_execution.get("artifact") or {}
        review = prior_code.get("review") or {}
        prompt = REWORK_PROMPT.format(
            gdd=gdd,
            spec=impl_spec,
            static_issues=prior_execution.get("error") or "(none)",
            loaded=exec_artifact.get("loaded", "unknown"),
            console_errors=exec_artifact.get("console_errors", []),
            canvas_rendered=exec_artifact.get("canvas_rendered", "unknown"),
            input_response=exec_artifact.get("input_response_detected", "unknown"),
            review_issues=(review.get("spec_fidelity_issues", []) + review.get("quality_issues", [])) or "(none)",
            previous_html=(prior_code.get("artifact") or {}).get("html", ""),
        )

    raw = llm.invoke(prompt)
    html = _strip_fences(raw.content if hasattr(raw, "content") else str(raw))

    error = None
    if not html.lstrip().lower().startswith("<!doctype html"):
        error = "Generated output does not start with <!DOCTYPE html>"

    out_dir = stage_dir(Path(state["run_dir"]), 4, "code", attempt)
    write_text(out_dir, "game.html", html)

    return {
        "code": {
            "status": "passed" if error is None else "failed_needs_rework",
            "attempt": attempt,
            "artifact": {"html": html},
            "review": None,
            "error": error,
        }
    }
