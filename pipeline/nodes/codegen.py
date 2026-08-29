import re
from pathlib import Path

from config import CODEGEN_MAX_TOKENS
from pipeline.llm import get_generation_llm
from pipeline.output import stage_dir, write_text
from pipeline.retry import invoke_with_retry, PipelineError, NODE_TIMEOUTS, NODE_MAX_ATTEMPTS
from pipeline.schemas import RunState

PROMPT = """You are a game programmer. Write ONE complete, self-contained HTML file that 
implements the game described below in Phaser 3.

Game Design Document:
{gdd}

Implementation Spec:
{spec}

Visual Specification:
{visual_spec}

Hard requirements:
- Output a single HTML file starting with <!DOCTYPE html>. Nothing before it, nothing 
after the closing </html> tag — no markdown fences, no commentary.
- Phaser 3 is PRELOADED as a global `Phaser` variable (available as `window.Phaser`). Do NOT include any <script src=\"...\"> tags for Phaser or any other external library. If you see an error about external script tags, REMOVE them entirely - do not replace them with other loading methods.
- A procedural particle library is available as `window.ParticleEngine` (also exposed as `window.Vector2`, `window.Particle`, and `window.ParticleEmitter` for convenience). Use this for particle effects instead of implementing your own particle system.\n- A procedural art library is available as `window.Art` (also exposed as `window.SoftCircle`, `window.SoftRect`, `window.Noise`, and `window.Gradient`). Use this for soft shapes, noise textures, and gradients instead of hard-edged graphics primitives.\n- Use the procedural UI classes from `window.UIKit` (Button, ProgressBar, Popup) for all UI elements, configuring them with the visual specification provided.
- Use the procedural UI classes from `window.UIKit` (Button, ProgressBar, Popup) for all UI elements, configuring them with the visual specification provided.\n- When using window.UIKit.Button, the constructor signature is (scene, x, y, text, styles, callback, width, height). The callback should be a function that handles the button press. The styles object should contain button_states and text_styles matching the visual spec.\\n- Generate ALL textures procedurally at runtime via graphics.generateTexture(). Never call\\nthis.load.image, this.load.audio, this.load.spritesheet, or reference any image/audio file \nby path or extension (.png, .jpg, .mp3, .wav, etc.) anywhere in the code.
- Use the Web Audio API directly (new AudioContext(), oscillators) for any sound. No audio files.
- Audio must start muted: create AudioContext and create a gain node connected to the destination, set gain to 0 initially. After first user interaction (pointerdown, keyup, etc.), set gain to 1 to unmute. Do not call AudioContext.resume() or HTMLAudioElement.play().
- On first user interaction (pointerdown, keyup, etc.), if the game is in the start state, transition to the gameplay state.
- After the tutorial phase, the game should transition to the core gameplay loop, but the game state should remain as a single 'playing' state for simplicity, with a tutorial flag to control tutorial UI.
- Expose a state property on the game instance (e.g., this.state) that reflects the current gameplay state ('start', 'playing', 'gameover', etc.) for validation purposes.
- The delta-time variable in update(time, delta) must be named exactly 'dt' (e.g. \n`const dt = delta / 1000;`). Never use 'deltaTime', 'elapsed', or 'elapsedTime'.
- Implement a Phaser.Game with at least one Phaser.Scene that has create() and update() \nmethods, and make the described controls and win/lose condition actually work.
- Delegate every class before it is referenced (e.g. before it appears in a `scene: [[]] \narray), to avoid ReferenceError: Cannot access '<Class>' before initialization.
- Expose the Phaser.Game instance as `window.__GAME__` immediately after creation for \nsemantic validation (e.g. `window.__GAME__ = game;`).
- Create the CTA button (text like \"INSTALL NOW\" or \"PLAY FULL VERSION\") inside `create()`, \nat the same time as the rest of the scene — NOT lazily inside your game-over/win/lose \nfunction. Store it as `this.ctaButton` immediately in `create()` and call `.setVisible(false)` \non it there; only call `.setVisible(true)` on it when the game reaches its end screen. \n`this.ctaButton` must be a real, already-constructed Phaser game object from the moment \n`create()` returns — validation checks for `this.ctaButton` existing while the game is still \nin progress, before any win/lose state is reached, so creating it only when the game ends \nwill fail validation even though the button itself works correctly once shown. The CTA \nbutton must have a `pointerdown` handler that calls `mraid.open(\"https://example.com\")` if \n`mraid` is available, otherwise `window.open(\"https://example.com\", \"_blank\")`.
- Never call `mraid.ready()` yourself — that is fired BY the host bridge, not something \ncreative code invokes (a real ad network's bridge may not even expose a callable `.ready`, \nso calling it can throw and crash the ad on load). Instead, gate your game's start on the \nbridge telling you it's ready and visible: if `typeof mraid !== 'undefined'`, wait for both \n`mraid.addEventListener('ready', ...)` (or `mraid.getState() !== 'loading'` if it already \nfired before you attached the listener) AND `mraid.isViewable()` being true (listen for \n`mraid.addEventListener('viewableChange', (viewable) => ...)` and start/pause the Phaser \ngame loop accordingly) before starting gameplay. If `mraid` is undefined, start immediately \nas normal — MRAID is not guaranteed to be present outside an ad network placement.
- Track elapsed time using the 'dt' parameter in your update() method. Use this to implement \nsession timing: ensure the tutorial phase lasts approximately {tutorial_duration_seconds} \nseconds, then transition to the core gameplay loop. Ensure the total session lasts \napproximately {target_session_seconds} seconds (tutorial + core loop), then automatically \ntransition to the GameOver state. Encourage the first meaningful interaction (pointerdown/keyup) \nto occur within {time_to_first_interaction_target_seconds} seconds for optimal retention.

"""

REWORK_PROMPT = PROMPT + """
Your previous attempt failed. Here is the real evidence of what went wrong — fix these 
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

Remember: The game MUST include MRAID integration:
- `this.ctaButton` created in create() (hidden via setVisible(false)), not created lazily 
inside the game-over/win/lose function — shown via setVisible(true) only when the game ends
- CTA button with mraid.open() handler
- Gameplay start gated on `mraid.addEventletner('ready', ...)` + `mraid.isViewable()` 
(via `viewableChange`) when `mraid` is present — never call `mraid.ready()` yourself
- window.__GAME__ exposure
"""

def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r'^```(?:html)?\\s*$', '', text, flags=re.MULTILINE)
    return text.strip()

def codegen(state: RunState) -> dict:
    gdd = state["design"]["artifact"]
    # Handle case where spec or its artifact might be None
    spec_dict = state.get("spec", {})
    if spec_dict is None:
        spec_dict = {}
    impl_spec = spec_dict.get("artifact", {})
    if impl_spec is None:
        impl_spec = {}
    visual_spec_dict = state.get("visual_spec", {})
    if visual_spec_dict is None:
        visual_spec_dict = {}
    visual_spec = visual_spec_dict.get("artifact", {})
    if visual_spec is None:
        visual_spec = {}
    prior_code = state.get("code") or {}
    prior_execution = state.get("execution") or {}
    attempt = prior_code.get("attempt", 0) + 1
    llm = get_generation_llm(temperature=0.3, max_tokens=CODEGEN_MAX_TOKENS, node="codegen")

    # Extract timing fields from impl_spec with defaults
    tutorial_duration_seconds = impl_spec.get("tutorial_duration_seconds", 5)
    target_session_seconds = impl_spec.get("target_session_seconds", 30)
    time_to_first_interaction_target_seconds = impl_spec.get("time_to_first_interaction_target_seconds", 4)

    if attempt == 1:
        prompt = PROMPT.format(
            gdd=gdd, 
            spec=impl_spec, 
            visual_spec=visual_spec,
            tutorial_duration_seconds=tutorial_duration_seconds,
            target_session_seconds=target_session_seconds,
            time_to_first_interaction_target_seconds=time_to_first_interaction_target_seconds
        )
    else:
        exec_artifact = prior_execution.get("artifact") or {}
        review = prior_code.get("review") or {}
        prompt = REWORK_PROMPT.format(
            gdd=gdd,
            spec=impl_spec,
            visual_spec=visual_spec,
            static_issues=prior_execution.get("error") or "(none)",
            loaded=exec_artifact.get("loaded", "unknown"),
            console_errors=exec_artifact.get("console_errors", []),
            canvas_rendered=exec_artifact.get("canvas_rendered", "unknown"),
            input_response=exec_artifact.get("input_response_detected", "unknown"),
            review_issues=(review.get("spec_fidelity_issues", []) + review.get("quality_issues", [])) or "(none)",
            previous_html=(prior_code.get("artifact") or {}).get("html", ""),
            tutorial_duration_seconds=tutorial_duration_seconds,
            target_session_seconds=target_session_seconds,
            time_to_first_interaction_target_seconds=time_to_first_interaction_target_seconds
        )

    try:
        raw = invoke_with_retry(
            lambda: llm.invoke(prompt),
            node="codegen",
            timeout_seconds=NODE_TIMEOUTS.get("codegen", 180),
            max_attempts=NODE_MAX_ATTEMPTS.get("codegen", 3),
        )
    except PipelineError as pe:
        # Return structured error state
        return {
            "code": {
                "status": "failed_needs_rework",
                "attempt": attempt,
                "artifact": {"html": ""},
                "review": None,
                "error": f"[{pe.category.value}] {pe.message}",
            }
        }

    html = _strip_fences(raw.content if hasattr(raw, "content") else str(raw))

    error = None
    finish_reason = getattr(raw, "response_metadata", {}).get("finish_reason")
    if finish_reason == "length":
        # The model hit CODEGEN_MAX_TOKENS mid-generation. The output is truncated —
        # it may still happen to parse/execute (e.g. cut off inside a trailing comment),
        # but treating it as complete would be exactly the silently-broken-artifact
        # failure mode this pipeline exists to catch.
        error = f"Generation truncated: hit max_tokens ({CODEGEN_MAX_TOKENS}) before finishing (finish_reason=length)"
    elif not html.lstrip().lower().startswith("<!doctype html>"):
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