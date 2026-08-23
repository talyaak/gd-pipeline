import re

from pipeline.llm import get_generation_llm
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
- Load Phaser 3 from a CDN: <script src="https://cdn.jsdelivr.net/npm/phaser@3/dist/phaser.min.js"></script>
- Generate ALL textures procedurally at runtime via graphics.generateTexture(). Never call \
this.load.image, this.load.audio, this.load.spritesheet, or reference any image/audio file \
by path or extension (.png, .jpg, .mp3, .wav, etc.) anywhere in the code.
- Use the Web Audio API directly (new AudioContext(), oscillators) for any sound. No audio \
files.
- The delta-time variable in update(time, delta) must be named exactly 'dt' (e.g. \
`const dt = delta / 1000;`). Never use 'deltaTime', 'elapsed', or 'elapsedTime'.
- Implement a Phaser.Game with at least one Phaser.Scene that has create() and update() \
methods, and make the described controls and win/lose condition actually work.
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:html)?\s*\n", "", text)
    text = re.sub(r"\n```\s*$", "", text)
    return text.strip()


def codegen(state: RunState) -> dict:
    gdd = state["design"]["artifact"]
    impl_spec = state["spec"]["artifact"]
    llm = get_generation_llm(temperature=0.3, max_tokens=16000)
    raw = llm.invoke(PROMPT.format(gdd=gdd, spec=impl_spec))
    html = _strip_fences(raw.content if hasattr(raw, "content") else str(raw))

    error = None
    if not html.lstrip().lower().startswith("<!doctype html"):
        error = "Generated output does not start with <!DOCTYPE html>"

    return {
        "code": {
            "status": "passed" if error is None else "failed_needs_rework",
            "attempt": 1,
            "artifact": {"html": html},
            "review": None,
            "error": error,
        }
    }
