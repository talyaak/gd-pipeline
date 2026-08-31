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
- A procedural particle library is available as `window.ParticleEngine` (also exposed as `window.Vector2`, `window.Particle`, and `window.ParticleEmitter` for convenience). Use this for particle effects instead of implementing your own particle system.
- A procedural art library is available as `window.Art` (also exposed as `window.SoftCircle`, `window.SoftRect`, `window.Noise`, and `window.Gradient`). Use this for soft shapes, noise textures, and gradients instead of hard-edged graphics primitives.
- Use the procedural UI classes from `window.UIKit` (Button, ProgressBar, Popup) for all UI elements, configuring them with the visual specification provided.
- **You MUST instantiate these classes with `new`** — e.g., `new window.UIKit.Button(...)`, `new window.UIKit.ProgressBar(...)`, `new window.UIKit.Popup(...)`. They are ES6 classes, not factory functions; calling them without `new` throws "Class constructor cannot be invoked without 'new'".
- When using window.UIKit.Button, the constructor signature is (scene, x, y, text, styles, callback, width, height). The callback should be a function that handles the button press. The styles object should contain button_states and text_styles matching the visual spec.
- Generate ALL textures procedurally at runtime via graphics.generateTexture(). Never call
this.load.image, this.load.audio, this.load.spritesheet, or reference any image/audio file
by path or extension (.png, .jpg, .mp3, .wav, etc.) anywhere in the code.
- Use the Web Audio API directly (new AudioContext(), oscillators) for any sound. No audio files.
- Audio must start muted: create AudioContext and create a gain node connected to the destination, set gain to 0 initially. After first user interaction (pointerdown, keyup, etc.), set gain to 1 to unmute. Do not call AudioContext.resume() or HTMLAudioElement.play().
- On first user interaction (pointerdown, keyup, etc.), if the game is in the start state, transition to the gameplay state.
- Expose the Phaser.Game instance as `window.__GAME__` immediately after creation for
semantic validation (e.g. `window.__GAME__ = game;`).
- **CRITICAL: Initialize score registry for validation**: right after `window.__GAME__ = game;`, call `game.registry.set('score', 0)` and `game.registry.set('gameOver', false)`.
- **CRITICAL: Track session time on the Game instance**: in your main scene's update(), update `this.game.sessionTime = (this.game.sessionTime || 0) + delta;` so the validator can measure engagement.
- **CRITICAL: Increment score in registry for validation**: in update(), while player is alive, call `this.game.registry.inc('score', 1)` — this proves active gameplay to the validator.
- Create the CTA button (text like "INSTALL NOW" or "PLAY FULL VERSION") inside `create()`,
at the same time as the rest of the scene — NOT lazily inside your game-over/win/lose 
function. Store it as `this.ctaButton` immediately in `create()` and call `.setVisible(false)` 
on it there; only call `.setVisible(true)` on it when the game reaches its end screen. 
`this.ctaButton` must be a real, already-constructed Phaser game object from the moment 
`create()` returns — validation checks for `this.ctaButton` existing while the game is still 
in progress, before any win/lose state is reached, so creating it only when the game ends 
will fail validation even though the button itself works correctly once shown. The CTA 
button must have a `pointerdown` handler that calls `mraid.open(\"https://example.com\")` if 
`mraid` is available, otherwise `window.open(\"https://example.com\", \"_blank\")`.
- Never call `mraid.ready()` yourself — that is fired BY the host bridge, not something 
creative code invokes (a real ad network's bridge may not even expose a callable `.ready`, 
so calling it can throw and crash the ad on load). Instead, gate your game's start on the 
bridge telling you it's ready and visible: if `typeof mraid !== 'undefined'`, wait for both 
`mraid.addEventListener('ready', ...)` (or `mraid.getState() !== 'loading'` if it already 
fired before you attached the listener) AND `mraid.isViewable()` being true (listen for 
`mraid.addEventListener('viewableChange', (viewable) => ...)` and start/pause the Phaser 
game loop accordingly) before starting gameplay. If `mraid` is undefined, start immediately 
as normal — MRAID is not guaranteed to be present outside an ad network placement.

CONCRETE MRAID GATING IMPLEMENTATION (copy this pattern exactly):
```javascript
// After window.__GAME__ = game; initialize score registry for validation
game.registry.set('score', 0);
game.registry.set('gameOver', false);

if (typeof mraid !== 'undefined') {{
  // Per MRAID spec: listen for ready event, don't call ready()
  if (mraid.getState() === 'loading') {{
    mraid.addEventListener('ready', () => {{
      // Bridge is ready, now gate on viewable
      if (mraid.isViewable()) {{
        startGameplay();
      }} else {{
        mraid.addEventListener('viewableChange', (viewable) => {{
          if (viewable) startGameplay();
        }});
      }}
    }});
  }} else if (mraid.isViewable()) {{
    startGameplay();
  }} else {{
    mraid.addEventListener('viewableChange', (viewable) => {{
      if (viewable) startGameplay();
    }});
  }}
}} else {{
  // No MRAID — game can start immediately
  startGameplay();
}}

// Gameplay start function - called when MRAID is ready+viewable (or immediately if no MRAID)
function startGameplay() {{
  // Game starts immediately (already running)
  // This is where you'd unpause game loop if gating on MRAID
  console.log('MRAID: Gameplay started (ready + viewable)');
}}
```

Then in your PlayScene's update(), track session time on the Game instance for validation:
```javascript
update(time, delta) {{
  const dt = delta / 1000;
  // ... your game logic ...

  // CRITICAL: Update sessionTime on the Game instance (not scene) for validation
  this.game.sessionTime = (this.game.sessionTime || 0) + delta;

  // CRITICAL: Increment score in registry for validation (proves active gameplay)
  if (this.player && this.player.alive) {{
    this.game.registry.inc('score', 1);
  }}
}}
```

Your main gameplay scene MUST be named 'PlayScene' (includes 'play' for scene-based validation fallback):
```javascript
class PlayScene extends Phaser.Scene {{
  constructor() {{
    super('PlayScene');
  }}
  // ...
}}
```

- To support custom close buttons required by some ad networks, set mraid.expandProperties.useCustomClose = true and create a close button (using window.UIKit.Button) positioned in the top-right corner of the expanded ad that calls mraid.close() when clicked. The close button should be hidden initially and shown when the ad is expanded (you can detect expansion via mraid.addEventListener('stateChange', ...) or by checking mraid.getState() === 'expanded').
- Track elapsed time using the 'dt' parameter in your update() method. Use this to implement
session timing: ensure the tutorial phase lasts approximately {tutorial_duration_seconds}
seconds, then transition to the core gameplay loop. Ensure the total session lasts
approximately {target_session_seconds} seconds (tutorial + core loop), then automatically
transition to the GameOver state. Encourage the first meaningful interaction (pointerdown/keyup)
to occur within {time_to_first_interaction_target_seconds} seconds for optimal retention.
- The delta-time variable in update(time, delta) must be named exactly 'dt' (e.g.
`const dt = delta / 1000;`). Never use 'deltaTime', 'elapsed', or 'elapsedTime'.
- Implement a Phaser.Game with at least one Phaser.Scene that has create() and update()
methods, and make the described controls and win/lose condition actually work.
- Delegate every class before it is referenced (e.g. before it appears in a `scene: [[]]
array), to avoid ReferenceError: Cannot access '<Class>' before initialization.

Do not economize on any of the requirements above (MRAID gating, muted-audio-until-interaction,
window.__GAME__ exposure, the CTA button structure, close-button support) even if a shorter or
simpler-looking implementation seems sufficient — these are compliance/trust-boundary
requirements, not stylistic preferences, and a "simpler" version that skips one of them will
fail validation or break on a real ad network. Apply minimal/no-unnecessary-code thinking to
everything else (game mechanics, visuals, structure), but not to this list.


KNOWN GOOD PATTERN — copy this exact structure for the validation-critical parts:
```html
<!DOCTYPE html>
<html>
<head><title>Your Game Title</title></head>
<body>
<script>
class PlayScene extends Phaser.Scene {{
    constructor() {{
        super('PlayScene');  // MUST include 'play' or 'game' for scene validation
    }}
    create() {{
        // ... your setup: procedural textures, player, CTA button (hidden), etc. ...
        
        // MRAID gating - gate gameplay on ready + viewable, never call mraid.ready()
        if (typeof mraid !== 'undefined') {{
            if (mraid.getState() === 'loading') {{
                mraid.addEventListener('ready', () => {{
                    if (mraid.isViewable()) startGameplay();
                    else mraid.addEventListener('viewableChange', (v) => {{ if (v) startGameplay(); }});
                }});
            }} else if (mraid.isViewable()) {{
                startGameplay();
            }} else {{
                mraid.addEventListener('viewableChange', (v) => {{ if (v) startGameplay(); }});
            }}
        }} else {{
            startGameplay();
        }}
        
        function startGameplay() {{
            console.log('MRAID: Gameplay started (ready + viewable)');
        }}
    }}
    update(time, delta) {{
        const dt = delta / 1000;
        // ... your game logic ...
        
        // CRITICAL: Update sessionTime on Game instance for validation
        this.game.sessionTime = (this.game.sessionTime || 0) + delta;
        
        // CRITICAL: Increment score in registry for validation
        if (this.player && this.player.alive) {{
            this.game.registry.inc('score', 1);
        }}
    }}
}}

var game = new Phaser.Game({{
    type: Phaser.AUTO,
    width: 800,
    height: 600,
    scene: [PlayScene],
}});
window.__GAME__ = game;
// CRITICAL: Initialize score registry for validation
game.registry.set('score', 0);
game.registry.set('gameOver', false);
</script>
</body>
</html>
```
"""

REWORK_PROMPT = PROMPT + """Your previous attempt failed. Here is the real evidence of what went wrong — fix these 
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
- Gameplay start gated on `mraid.addEventListener('ready', ...)` + `mraid.isViewable()`
(via `viewableChange`) when `mraid` is present — never call `mraid.ready()` yourself
- window.__GAME__ exposure
- **game.registry.set('score', 0)** + **game.registry.inc('score', 1)** in update()
- **this.game.sessionTime** updated in update()
- Main scene named **'PlayScene'** (includes 'play' for scene validation)
"""

def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r'^```(?:html)?\s*$', '', text, flags=re.MULTILINE)
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