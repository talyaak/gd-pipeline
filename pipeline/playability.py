"""Vision-model playability check.

Every other execution check is a technical proxy: canvas has pixels, a
before/after screenshot diff registered as "input response", a registry
number ticked up. All of those can pass on a game that's genuinely frozen on
its own start screen — confirmed by hand on a run that passed every one of
them and never advanced past "Move: A/D or Arrow Keys" after 25+ seconds of
real synthetic input. This check asks a model to actually look at the two
screenshots the harness already captures (before any input, after the full
input+observation window) and make the same judgment call a human glancing
at the screen would.
"""
import base64
import json

from langchain_core.messages import HumanMessage

from pipeline.llm import get_review_llm
from pipeline.retry import invoke_with_retry
from pipeline.schemas import PlayabilityReport

PLAYABILITY_PROMPT = """You are looking at two screenshots from an automated test of an HTML5 game:
- Screenshot 1: captured immediately after the page loaded, before any input was sent.
- Screenshot 2: captured after roughly 25 seconds during which the test harness pressed keys, clicked, and dragged on the canvas, then just watched.

Judge ONE thing: does this look like a real, playable game that a human could actually play — not whether it's pretty, not whether it matches a design spec. Specifically:
- Did it visibly progress past a start/menu/tutorial screen? (the same "press to start" style instructions still on screen in both shots is a bad sign)
- Is there a visible, recognizable game element — a player, obstacles, a changing score display, anything — not just an empty or static background?
- Do the two screenshots differ in a way consistent with real gameplay actually happening, not just a cursor or a single static UI element moving?

Be skeptical and literal. If the second screenshot still looks like a frozen start screen, or you can't tell whether anything actually happened, that is NOT playable. A false pass here ships a broken game; a false fail just costs one retry — when genuinely unsure, fail it.

Return ONLY a JSON object, no other text: {"playable": true or false, "reasoning": "one or two sentences, specific to what you actually see in the two screenshots"}"""


def check_playability(before_png: bytes, after_png: bytes, node: str = "playability") -> PlayabilityReport:
    llm = get_review_llm(node=node)
    before_b64 = base64.b64encode(before_png).decode("utf-8")
    after_b64 = base64.b64encode(after_png).decode("utf-8")
    message = HumanMessage(content=[
        {"type": "text", "text": PLAYABILITY_PROMPT},
        {"type": "text", "text": "Screenshot 1 (before any input):"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{before_b64}"}},
        {"type": "text", "text": "Screenshot 2 (after ~25s of input + observation):"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{after_b64}"}},
    ])

    raw = invoke_with_retry(
        lambda: llm.invoke([message]),
        node=node,
        timeout_seconds=60,
        max_attempts=2,
    )
    content = raw.content if hasattr(raw, "content") else str(raw)
    # Anthropic vision responses can come back as a list of content blocks.
    if isinstance(content, list):
        content = "".join(block.get("text", "") if isinstance(block, dict) else str(block) for block in content)

    start = content.find("{")
    end = content.rfind("}") + 1
    if start < 0 or end <= start:
        raise ValueError(f"Playability check returned no parseable JSON: {content[:200]!r}")
    data = json.loads(content[start:end])
    return PlayabilityReport(**data)
