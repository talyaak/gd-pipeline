"""Stage 2 (APK-as-input): write a mechanics spec per captured gameplay video.

For each video in sources.json: sample frames deterministically (evenly spaced,
skipping the opening load screen), encode them as JPEG data URLs, and make ONE
vision-model call per video using the configured VISION_MODEL. The exact prompt
is the SPEC_WRITER_PROMPT constant below. Output: specs/<slug>_spec.json.

Usage: python tools/apk_input/spec_writer.py [--repo-root PATH]
"""

import base64
import json
import os
import re
import sys
import time
from pathlib import Path

import cv2

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic import BaseModel, Field, ValidationError  # noqa: E402

# Same OpenRouter wiring as pipeline/graph.py (kept self-contained so this
# tool works on any branch).
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
VISION_MODEL = os.getenv("VISION_MODEL", "openrouter/free")


class MechanicsSpec(BaseModel):
    """Structured output contract for the spec-writer vision call."""

    core_loop: list[str] = Field(description="4-7 ordered steps a player repeats minute to minute")
    controls: list[str] = Field(description="Gesture -> effect, as visible from UI affordances")
    progression: list[str] = Field(description="Currencies, unlock order, expansion axes")
    session_feel: str = Field(description="Pacing, density, juice level, session length, audience vibe")
    confidence_notes: list[str] = Field(description="What frames cannot show; seen vs inferred per claim")

# Frames sampled per video: evenly spaced between 5% and 95% of the runtime.
# Payload note: the free vision model returns empty responses for large
# multimodal inputs (~>160 KB of base64 JPEG), so frames stay small.
NUM_FRAMES = 8
FRAME_MAX_WIDTH = 400
JPEG_QUALITY = 60

# ---------------------------------------------------------------------------
# EXACT spec-writer prompt (one call per video; frames are attached as images)
# ---------------------------------------------------------------------------
SPEC_WRITER_PROMPT = """\
You are a game-mechanics analyst. You are given {num_frames} frames sampled \
evenly from a single gameplay video of the mobile game **{game}**.

Video title: "{title}"

TASK: write a mechanics spec describing what you can actually SEE in these \
frames. This spec will be used to build a playable clone of the core loop, so \
concrete, observable details are worth more than plausible guessing.

Return a single JSON object with exactly these keys:
- "core_loop": array of strings, the 4-7 ordered steps a player repeats \
minute to minute (e.g. "harvest crop -> sell at stall -> buy plot -> unlock \
crop").
- "controls": array of strings, how the player interacts (tap, drag, swipe, \
hold) and what each gesture does, as visible from UI affordances.
- "progression": array of strings, how the game deepens over minutes/hours: \
currencies, unlock order, expansion axes (buildings, animals, crops, areas).
- "session_feel": string, pacing, screen density, juice/animation level, \
estimated session length, target audience vibe.
- "confidence_notes": array of strings, REQUIRED: everything a frame sample \
CANNOT tell you (real-time vs turn timing, audio, exact numbers, off-screen \
systems) and mark each spec claim as seen / inferred.

Rules:
- The frames ARE real gameplay of the named game — that is ground truth, not \
a hypothesis. Your job is to reverse-engineer the loop from what the frames \
show, not to judge whether a loop is provable from stills.
- Static screenshots still reveal game systems: visible menus, buildings, \
crops, animals, currencies, level/counter numbers, map areas. Derive the \
core loop and progression those elements imply.
- Every array entry MUST start with a tag: "[seen] " (element directly \
visible in a frame) or "[inferred] " (system implied by visible UI). Never \
leave an array empty when any game system is visible; if something is \
genuinely absent from all frames, say so in confidence_notes instead.
- Do not pad. Wrong guesses are worse than "[inferred]" hedges.
- Respond with ONLY the JSON object — no markdown fences, no prose.

NOTE (tooling, not part of your task): plain text output is used instead of \
function calling because the free vision model does not support tool calls \
with image input.
"""


def sample_frames(video_path: Path, num_frames: int) -> list[bytes]:
    """Sample num_frames JPEG-encoded frames evenly between 5% and 95%."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    duration = total / fps
    frames = []
    for i in range(num_frames):
        t = duration * (0.05 + 0.90 * i / (num_frames - 1))
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        if w > FRAME_MAX_WIDTH:
            scale = FRAME_MAX_WIDTH / w
            frame = cv2.resize(frame, (FRAME_MAX_WIDTH, int(h * scale)))
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if ok:
            frames.append(buf.tobytes())
    cap.release()
    return frames


def write_spec(slug: str, source: dict, videos_dir: Path, out_dir: Path) -> Path:
    video_path = videos_dir / source["local_file"]
    frames = sample_frames(video_path, NUM_FRAMES)
    if not frames:
        raise RuntimeError(f"no frames sampled from {video_path}")

    prompt = SPEC_WRITER_PROMPT.format(
        num_frames=len(frames), game=slug.replace("_", " ").title(), title=source["title"]
    )
    content = [{"type": "text", "text": prompt}] + [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(f).decode()}"},
        }
        for f in frames
    ]

    llm = ChatOpenAI(
        model=VISION_MODEL,
        temperature=0.3,
        # This model is a reasoning model: reasoning tokens come out of the
        # same budget, so the cap must leave room for the JSON output.
        max_tokens=10000,
        base_url=OPENROUTER_BASE_URL,
        api_key=os.getenv("OPENROUTER_API_KEY"),
        default_headers={
            "HTTP-Referer": "https://github.com/talyaak/gd-pipeline",
            "X-Title": "gd-pipeline",
        },
    )
    # Plain text call (no function calling): the free vision model does not
    # support tool calls with image input. Response is raw JSON, parsed and
    # validated locally into MechanicsSpec. Known failure modes, all retried:
    # empty bodies (throttling) and truncated JSON (output budget exhausted
    # by reasoning tokens).
    last_error: Exception | None = None
    for attempt in range(6):
        if attempt:
            # Degenerate/empty outputs cluster under provider rate pressure;
            # a real cooldown between attempts works better than tight spins.
            time.sleep(30)
        raw = ""
        try:
            resp = llm.invoke([{"role": "user", "content": content}])
            raw = resp.content.strip() if isinstance(resp.content, str) else ""
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", raw).strip()
            start, end = raw.find("{"), raw.rfind("}")
            if start == -1 or end == -1:
                raise ValueError(f"no JSON object in response ({raw[:80]!r})")
            spec = MechanicsSpec.model_validate_json(raw[start:end + 1])
            if not any([spec.core_loop, spec.controls, spec.progression, spec.session_feel]):
                raise ValueError("model returned an all-empty spec (degenerate output)")
            break
        except (ValueError, ValidationError) as e:
            last_error = e
            print(
                f"[spec_writer] {slug}: attempt {attempt + 1}/6 failed "
                f"({str(e)[:120]}), cooling down 30s"
            )
    else:
        raise RuntimeError(f"vision model failed to produce a valid spec for {slug}: {last_error}")

    result = {
        "slug": slug,
        "source": {k: source[k] for k in ("video_id", "url", "title", "channel", "duration_s")},
        "model": VISION_MODEL,
        "frames_sampled": len(frames),
        "spec": spec.model_dump(),
    }
    out_path = out_dir / f"{slug}_spec.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[spec_writer] {slug}: spec written -> {out_path}")
    return out_path


def main() -> None:
    base = Path(__file__).resolve().parent
    sources = json.loads((base / "sources.json").read_text(encoding="utf-8"))
    out_dir = base / "specs"
    out_dir.mkdir(parents=True, exist_ok=True)
    for slug, source in sources.items():
        if (out_dir / f"{slug}_spec.json").exists():
            print(f"[spec_writer] {slug}: spec exists, skipping")
            continue
        write_spec(slug, source, base / "videos", out_dir)


if __name__ == "__main__":
    main()
