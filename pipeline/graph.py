"""AI Game Design Pipeline — LangGraph graph with Cycle X + HITL.

Step 1: Genre Research — structured analysis of a game genre.
Step 2: GDD Generation — Cycle X auto-review + HITL human approval gate.
Step 3: Implementation Spec — Cycle X auto-review for technical completeness.
Step 4: Code Generation — produce a single-file HTML5 browser game.
Step 5: Code Review — Cycle X auto-review for playability and spec fidelity.

Cycle X pattern: Generate → Review → Fix → Repeat until quality threshold met.
HITL: Human-in-the-loop interrupt between GDD approval and impl spec generation.
"""

from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from pipeline import output
from pipeline.retry import invoke_with_retry
from pipeline.schemas import (
    CodeReview,
    GameDesignDocument,
    GddReview,
    GeneratedGame,
    GenreAnalysis,
    ImplSpecReview,
    ImplementationSpec,
)
from pipeline.validate import check_html_game

LLM_MODEL    = "gpt-4.1"   # generation tasks: GDD, impl spec, code
REVIEW_MODEL = "gpt-4.1-mini"   # review tasks: cheaper/faster (swap for e.g. gpt-4.1-mini)

# Maximum completion tokens per model (OpenAI hard limits)
_MODEL_OUTPUT_LIMITS: dict[str, int] = {
    "gpt-4o-mini":  16_384,
    "gpt-4.1-mini": 16_384,
    "gpt-4.1":      32_768,
    "gpt-5.2":      32_768,
}

def _max_tokens(model: str, want: int) -> int:
    """Cap *want* to the model's output-token limit."""
    return min(want, _MODEL_OUTPUT_LIMITS.get(model, 16_384))

MAX_GDD_ATTEMPTS       = 3
MAX_IMPL_SPEC_ATTEMPTS = 2
MAX_CODE_ATTEMPTS      = 3


# ---------------------------------------------------------------------------
# State: what flows through the graph
# ---------------------------------------------------------------------------
class PipelineState(TypedDict):
    genre: str
    analysis: GenreAnalysis | None
    gdd: GameDesignDocument | None
    gdd_review: GddReview | None
    gdd_attempt: int
    human_approved: bool
    human_feedback: str | None
    impl_spec: ImplementationSpec | None
    impl_spec_review: ImplSpecReview | None
    impl_spec_attempt: int
    code: GeneratedGame | None
    code_review: CodeReview | None
    code_attempt: int


# ---------------------------------------------------------------------------
# Node: research_genre
# ---------------------------------------------------------------------------
RESEARCH_PROMPT = """\
You are an expert game designer specializing in hyper-casual and casual HTML5 \
browser games for portals like CrazyGames, Poki, and itch.io.

Analyze the genre: **{genre}**

Your analysis should be practical and opinionated — aimed at a small team that \
needs to ship a fun, retainable browser game in this genre within a month. \
Focus on what actually matters for player retention on web game portals, not \
theory.

Be specific. Name real techniques, real games, real numbers where possible. \
"Add juice" is not useful — "add 2-frame hit-freeze + radial particle burst \
on enemy death" is useful.
"""


def research_genre(state: PipelineState) -> PipelineState:
    """Call the review model with structured output to produce a GenreAnalysis."""
    llm = ChatOpenAI(
        model=REVIEW_MODEL,
        temperature=0.3,
        max_tokens=2048,
    )

    structured_llm = llm.with_structured_output(GenreAnalysis, method="function_calling")

    analysis = invoke_with_retry(
        structured_llm, RESEARCH_PROMPT.format(genre=state["genre"])
    )

    path = output.save("01_genre_research", "analysis.json", analysis.model_dump())
    print(f"  [research_genre] Done → {output.rel(path)}")

    return {"analysis": analysis}


# ---------------------------------------------------------------------------
# Node: generate_gdd
# ---------------------------------------------------------------------------
GDD_PROMPT = """\
You are an expert game designer writing a concrete Game Design Document for a \
hyper-casual / casual HTML5 browser game.

The target platforms are web portals like CrazyGames, Poki, and itch.io. The \
game must be buildable by a small team (1-3 devs) within one month.

Genre: **{genre}**

Here is the genre research to base your design on:
{analysis_json}

Design ONE specific game — not a template. Pick a clear creative direction and \
commit to it. The GDD should be specific enough that a developer could start \
building tomorrow.

Priorities:
- Instant fun in the first 3 seconds (no tutorials, no menus)
- Core loop must work with 1-2 inputs (mouse click / tap + optional direction)
- Visual style must be achievable with free assets or simple geometric art
- MVP-first: cut everything that isn't essential to the core loop
- Juice is mandatory, not optional — list specific techniques with parameters
"""


REWORK_GDD_PROMPT = """\
You are an expert game designer REVISING a Game Design Document based on \
reviewer feedback. Keep what works, fix what doesn't.

Genre: **{genre}**

Genre research:
{analysis_json}

Previous GDD that needs improvement:
{previous_gdd_json}

{feedback_section}

Generate an improved GDD that addresses every issue. Do not lose the strengths. \
Be more specific, more concrete, more buildable.
"""


def _build_gdd_feedback_section(state: PipelineState) -> str:
    """Build the feedback section for the GDD rework prompt."""
    parts = []
    human_feedback = state.get("human_feedback")
    review = state.get("gdd_review")

    if human_feedback:
        parts.append(
            f"**HUMAN REVIEWER (highest priority):**\n{human_feedback}"
        )

    if review:
        parts.append(
            f"Automated reviewer feedback (score {review.score}/10):\n"
            f"Strengths (KEEP these): {'; '.join(review.strengths)}\n"
            f"Issues (MUST FIX): {'; '.join(review.issues)}\n"
            f"Suggestions (nice to have): {'; '.join(review.suggestions)}"
        )

    return "\n\n".join(parts)


def generate_gdd(state: PipelineState) -> PipelineState:
    """Take the genre analysis and produce a concrete game design document.

    On rework attempts, incorporates auto-review and/or human feedback.
    """
    llm = ChatOpenAI(
        model=LLM_MODEL,
        temperature=0.7,
        max_tokens=_max_tokens(LLM_MODEL, 32_768),
    )

    structured_llm = llm.with_structured_output(GameDesignDocument, method="function_calling")

    analysis_json = state["analysis"].model_dump_json()
    attempt = state.get("gdd_attempt", 0) + 1
    review = state.get("gdd_review")
    human_feedback = state.get("human_feedback")

    if (review and not review.passed) or human_feedback:
        # Rework: feed previous GDD + feedback into a focused rework prompt
        previous_gdd_json = state["gdd"].model_dump_json()
        prompt = REWORK_GDD_PROMPT.format(
            genre=state["genre"],
            analysis_json=analysis_json,
            previous_gdd_json=previous_gdd_json,
            feedback_section=_build_gdd_feedback_section(state),
        )
    else:
        # First attempt: use the original prompt
        prompt = GDD_PROMPT.format(
            genre=state["genre"],
            analysis_json=analysis_json,
        )

    gdd = invoke_with_retry(structured_llm, prompt)

    path = output.save("02_gdd", "gdd.json", gdd.model_dump(), attempt=attempt)
    print(f"  [generate_gdd] Attempt {attempt} → {output.rel(path)}")

    return {"gdd": gdd, "gdd_attempt": attempt, "human_feedback": None}


# ---------------------------------------------------------------------------
# Node: review_gdd
# ---------------------------------------------------------------------------
REVIEW_GDD_PROMPT = """\
Be concise: list at most 5 blocking issues and 5 suggestions; keep total \
output under 400 tokens.

You are a ruthless game design reviewer with 15 years of experience shipping \
hyper-casual HTML5 games on web portals (CrazyGames, Poki, itch.io).

Review this Game Design Document and decide if it's ready for implementation.

Genre: **{genre}**

GDD:
{gdd_json}

Score the GDD from 1-10 based on these criteria:
- **Specificity** (weight: 3x): Can a developer start building from this tomorrow? \
Are controls, mechanics, and numbers concrete — not vague platitudes?
- **Core loop clarity** (weight: 2x): Is the moment-to-moment gameplay crystal clear? \
Can you visualize exactly what the player does every 5 seconds?
- **Scope realism** (weight: 2x): Is the MVP achievable in 1-2 weeks by a small team? \
Or is it a disguised AAA pitch?
- **Juice / game feel** (weight: 1x): Are juice items specific with parameters, \
not just "add screen shake"?
- **Fun factor** (weight: 2x): Would this actually be fun to play for 2 minutes? \
Does the core mechanic have inherent satisfaction?

DESIGN COHERENCE CHECK — flag as a blocking issue if any of these are violated:
- If the game has N lanes/tracks/paths, the controls MUST include N-1 lateral \
movement inputs (e.g. 3 lanes → left/right inputs). A multi-lane game with \
only a single jump input does not use the lanes and is not fun.
- If the game has a dash/dodge mechanic, the controls must specify what triggers it.
- If the game has a fire/attack mechanic, the controls must specify the input.
- Every mechanic listed in core_loop must be achievable with the listed controls. \
If there is a mismatch (mechanic exists but no input for it), that is a blocker.

Scoring guide:
- 9-10: Ship it. Exceptional GDD, ready to build.
- 7-8: Good enough. Minor issues but a competent dev can fill the gaps.
- 5-6: Needs work. Too vague, scope too big, or core loop isn't fun.
- 1-4: Start over. Fundamental design problems.

Pass threshold: 7 or above.

Be specific in your feedback. "Needs more detail" is useless. \
"Core loop step 3 says 'dodge enemies' but doesn't specify enemy movement \
patterns, spawn rates, or how dodging feels different from walking" is useful.
"""


def review_gdd(state: PipelineState) -> PipelineState:
    """Review the GDD for quality and decide if it needs rework."""
    llm = ChatOpenAI(
        model=REVIEW_MODEL,
        temperature=0.3,
        max_tokens=512,
    )

    structured_llm = llm.with_structured_output(GddReview, method="function_calling")

    gdd_json = state["gdd"].model_dump_json()

    review = invoke_with_retry(
        structured_llm,
        REVIEW_GDD_PROMPT.format(genre=state["genre"], gdd_json=gdd_json),
    )

    attempt = state.get("gdd_attempt", 1)
    status = "passed" if review.passed and review.score >= 7 else "needs rework"
    path = output.save("02_gdd", "review.json", review.model_dump(), attempt=attempt)
    print(f"  [review_gdd] Score {review.score}/10 ({status}) → {output.rel(path)}")

    return {"gdd_review": review}


def should_rework_gdd(state: PipelineState) -> str:
    """Conditional edge: decide whether to rework the GDD or proceed to human review."""
    review = state["gdd_review"]
    attempt = state.get("gdd_attempt", 1)

    if review.passed and review.score >= 7:
        return "human_review_gdd"

    if attempt >= MAX_GDD_ATTEMPTS:
        # Avoid infinite loops — let the human decide after max auto attempts
        return "human_review_gdd"

    return "generate_gdd"


# ---------------------------------------------------------------------------
# Node: human_review_gdd (HITL interrupt)
# ---------------------------------------------------------------------------
def human_review_gdd(state: PipelineState) -> PipelineState:
    """Pause for human review of the GDD.

    Uses LangGraph interrupt() to hand control to the human.
    The human can approve or provide feedback to trigger a rework.
    """
    review = state["gdd_review"]
    gdd = state["gdd"]

    # Pause execution — return structured data for the CLI to display
    human_response = interrupt({
        "type": "gdd_review",
        "title": gdd.title,
        "one_liner": gdd.one_liner,
        "gdd": gdd.model_dump(),
        "auto_review_score": review.score,
        "auto_review_passed": review.passed,
        "strengths": review.strengths,
        "issues": review.issues,
        "suggestions": review.suggestions,
        "gdd_attempt": state.get("gdd_attempt", 1),
    })

    # Parse human response
    response_text = human_response.strip()
    if response_text.lower() in ("approve", "y", "yes", "ok", "lgtm"):
        return {"human_approved": True, "human_feedback": None}
    else:
        return {
            "human_approved": False,
            "human_feedback": response_text,
            "gdd_attempt": 0,  # Reset counter for fresh auto-review cycle
        }


def should_proceed_after_human_review(state: PipelineState) -> str:
    """Conditional edge: human approved → impl spec, rejected → rework GDD."""
    if state.get("human_approved"):
        return "generate_impl_spec"
    return "generate_gdd"


# ---------------------------------------------------------------------------
# Node: generate_impl_spec
# ---------------------------------------------------------------------------
IMPL_SPEC_PROMPT = """\
You are a senior game programmer writing the technical implementation spec for \
an HTML5 browser game. Your spec will be handed directly to a developer — it \
must be concrete enough to start coding from.

Game: **{title}**
Genre: **{genre}**

Game Design Document:
{gdd_json}
{gdd_issues_section}

Produce a complete implementation spec:

1. **Entities**: Every object in the game world. Include exact properties with \
types and default values. Think about what a developer needs in their class/struct.

2. **State machine**: Top-level game states with transitions. Cover the full \
lifecycle: load → play → die → retry.

3. **Balance tables**: EVERY tunable number in the game grouped by category. \
Player speed, enemy HP, spawn rates, score multipliers, difficulty ramp — all \
with concrete starting values and brief rationale for each.

4. **Scene flow**: Ordered list of screens/scenes.

5. **Asset manifest**: Every sprite, sound, and font needed for the MVP. \
Include dimensions, frame counts, and style notes. Keep it minimal — use \
geometric shapes and simple SFX where possible.

6. **Technical notes**: Canvas 2D vs WebGL, collision approach, performance \
budget (target 60fps on mid-range mobile), recommended libraries if any.

7. **Example chunks** (REQUIRED if the game uses chunk/pattern spawning): \
Include 3–5 concrete JSON chunk examples. At minimum: single obstacle, \
obstacle + coins, gap + warning. Each example must be valid JSON a dev can \
load. This is non-negotiable for buildability.

SCOPE: Fully specify core gameplay (entities, collision, spawning, scoring). \
For RNG algorithm, audio polyphony, exact UI hit-testing — write "implementer's \
choice" and do not over-specify. Keep total spec under 1000 lines.

Be ruthlessly practical. A developer should be able to `npm init` and start \
building from this spec.
"""


REWORK_IMPL_SPEC_PROMPT = """\
You are a senior game programmer REVISING a technical implementation spec based \
on reviewer and/or human feedback. Keep what works, fix what doesn't.

Game: **{title}**
Genre: **{genre}**

Game Design Document:
{gdd_json}

Previous implementation spec that needs improvement:
{previous_spec_json}

{feedback_section}

Generate an improved spec that addresses every issue. Do not lose the strengths. \
Every entity property needs a type and default value. Every balance number needs \
a rationale. Every asset needs dimensions.

If the game uses chunk spawning and example_chunks is empty or incomplete, add \
3–5 concrete JSON chunk examples. Keep total spec under 1000 lines — cut polish \
details before core gameplay.
"""


def _build_gdd_issues_for_impl_spec(state: PipelineState) -> str:
    """Build GDD reviewer issues to pass into impl spec — prevents propagation of known gaps."""
    review = state.get("gdd_review")
    if not review or not (review.issues or review.suggestions):
        return ""
    parts = [
        "GDD REVIEWER FEEDBACK — address these gaps in your impl spec before expanding:",
        "",
    ]
    if review.issues:
        parts.append("Issues to resolve: " + "; ".join(review.issues))
    if review.suggestions:
        parts.append("Suggestions to incorporate: " + "; ".join(review.suggestions))
    return "\n".join(parts)


def _build_impl_spec_feedback_section(state: PipelineState) -> str:
    """Build the feedback section for the impl spec rework prompt."""
    parts = []
    human_feedback = state.get("human_feedback")
    review = state.get("impl_spec_review")

    if human_feedback:
        parts.append(f"**HUMAN REVIEWER (highest priority):**\n{human_feedback}")

    if review:
        parts.append(
            f"Automated reviewer feedback (score {review.score}/10):\n"
            f"Strengths (KEEP these): {'; '.join(review.strengths)}\n"
            f"Issues (MUST FIX): {'; '.join(review.issues)}\n"
            f"Suggestions (nice to have): {'; '.join(review.suggestions)}"
        )

    return "\n\n".join(parts)


def generate_impl_spec(state: PipelineState) -> PipelineState:
    """Turn the GDD into a technical implementation spec.

    On rework attempts, incorporates review feedback to improve the spec.
    """
    llm = ChatOpenAI(
        model=LLM_MODEL,
        temperature=0.3,
        max_tokens=_max_tokens(LLM_MODEL, 32_768),
    )

    structured_llm = llm.with_structured_output(ImplementationSpec, method="function_calling")

    gdd_json = state["gdd"].model_dump_json()
    attempt = state.get("impl_spec_attempt", 0) + 1
    review = state.get("impl_spec_review")

    if (review and not review.passed) or state.get("human_feedback"):
        # Rework: feed previous spec + feedback (from reviewer and/or human)
        previous_spec_json = state["impl_spec"].model_dump_json()
        prompt = REWORK_IMPL_SPEC_PROMPT.format(
            title=state["gdd"].title,
            genre=state["genre"],
            gdd_json=gdd_json,
            previous_spec_json=previous_spec_json,
            feedback_section=_build_impl_spec_feedback_section(state),
        )
    else:
        gdd_issues_section = _build_gdd_issues_for_impl_spec(state)
        prompt = IMPL_SPEC_PROMPT.format(
            title=state["gdd"].title,
            genre=state["genre"],
            gdd_json=gdd_json,
            gdd_issues_section=gdd_issues_section,
        )

    impl_spec = invoke_with_retry(structured_llm, prompt)

    path = output.save(
        "03_impl_spec", "impl_spec.json", impl_spec.model_dump(), attempt=attempt
    )
    print(f"  [generate_impl_spec] Attempt {attempt} → {output.rel(path)}")

    return {"impl_spec": impl_spec, "impl_spec_attempt": attempt}


# ---------------------------------------------------------------------------
# Node: review_impl_spec
# ---------------------------------------------------------------------------
REVIEW_IMPL_SPEC_PROMPT = """\
You are a pragmatic technical reviewer evaluating an implementation spec for a \
hyper-casual HTML5 browser game. Target: MVP buildable in 1-2 weeks. Be strict \
on blockers, lenient on polish.

Game: **{title}**
Genre: **{genre}**

Implementation Spec:
{spec_json}

Score the spec from 1-10 based on these criteria:
- **Entity completeness** (weight: 2x): Core entities (player, obstacles, pickups) \
have properties with types and defaults. Minor entities can have gaps.
- **Balance table coverage** (weight: 2x): Key tunables (speed, spawn rates, scoring) \
present with values. Not every edge-case number needed for MVP.
- **State machine** (weight: 1x): Load → Play → GameOver → Retry covered. \
Transitions clear enough to implement.
- **Asset specificity** (weight: 1x): Enough to use procedural graphics or placeholders. \
Exact dimensions optional for MVP.
- **Buildability** (weight: 2x): Could a developer start coding the core loop \
without major clarifying questions? Perfect pseudocode and edge-case coverage \
are NOT required for MVP.

Scoring guide (MVP-focused):
- 9-10: Exceptional. Ready to code.
- 7-8: Good enough for MVP. Minor gaps OK. PASS.
- 5-6: Has core structure but significant gaps that would block implementation. \
List the 3-5 most critical blockers only.
- 1-4: Fundamental gaps. Missing core entities or unbuildable.

Pass threshold: 7 or above. When in doubt between 6 and 7, prefer 7 if the \
core loop is spec'd and a dev could make reasonable choices for the gaps.

Be specific but concise. Focus on blockers, not nice-to-haves.
"""


def review_impl_spec(state: PipelineState) -> PipelineState:
    """Review the implementation spec for completeness and buildability."""
    llm = ChatOpenAI(
        model=REVIEW_MODEL,
        temperature=0.3,
        max_tokens=512,
    )

    structured_llm = llm.with_structured_output(ImplSpecReview, method="function_calling")

    spec_json = state["impl_spec"].model_dump_json()

    review = invoke_with_retry(
        structured_llm,
        REVIEW_IMPL_SPEC_PROMPT.format(
            title=state["gdd"].title,
            genre=state["genre"],
            spec_json=spec_json,
        ),
    )

    attempt = state.get("impl_spec_attempt", 1)
    status = "passed" if review.passed and review.score >= 7 else "needs rework"
    path = output.save(
        "03_impl_spec", "review.json", review.model_dump(), attempt=attempt
    )
    print(f"  [review_impl_spec] Score {review.score}/10 ({status}) → {output.rel(path)}")

    return {"impl_spec_review": review}


def should_rework_impl_spec(state: PipelineState) -> str:
    """Conditional edge: pass → code gen, fail → human review (no auto-retry loop)."""
    review = state["impl_spec_review"]
    if review.passed and review.score >= 7:
        return "generate_code"
    return "human_review_impl_spec"


# ---------------------------------------------------------------------------
# Node: human_review_impl_spec (HITL interrupt)
# ---------------------------------------------------------------------------
def human_review_impl_spec(state: PipelineState) -> PipelineState:
    """Pause for human review of the implementation spec.

    When auto-review fails (e.g. 6/10), human can approve to proceed or
    provide feedback for one targeted rework — avoids token burn on retry loops.
    """
    review = state["impl_spec_review"]
    impl_spec = state["impl_spec"]
    gdd = state["gdd"]

    human_response = interrupt({
        "type": "impl_spec_review",
        "title": gdd.title,
        "auto_review_score": review.score,
        "auto_review_passed": review.passed,
        "strengths": review.strengths,
        "issues": review.issues,
        "suggestions": review.suggestions,
        "impl_spec_attempt": state.get("impl_spec_attempt", 1),
    })

    response_text = human_response.strip()
    if response_text.lower() in ("approve", "y", "yes", "ok", "lgtm"):
        return {"human_approved": True, "human_feedback": None}
    return {
        "human_approved": False,
        "human_feedback": response_text,
    }


def should_proceed_after_impl_review(state: PipelineState) -> str:
    """Conditional edge: human approved → code gen, rejected → rework impl spec."""
    if state.get("human_approved"):
        return "generate_code"
    return "generate_impl_spec"


# ---------------------------------------------------------------------------
# Node: generate_code — multi-pass generation
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    """Strip markdown code fences the model occasionally wraps output in."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```", 2)
        body = parts[1] if len(parts) > 1 else text
        if body.startswith("html"):
            body = body[4:]
        body = body.rsplit("```", 1)[0]
        return body.strip()
    return text


def _run_code_pass(llm, prompt: str) -> str:
    """Invoke one code-generation LLM pass and return clean HTML."""
    response = invoke_with_retry(llm, prompt)
    return _strip_fences(response.content)


CODE_PASS1_PROMPT = """\
Generate a complete, single-file Phaser 3 HTML5 game.

Game: **{title}** | Genre: **{genre}**

GDD:
{gdd_json}

Implementation Spec:
{spec_json}

PASS 1 — FOUNDATION
Build the full working game. Every system must be functional by end of this pass.

REQUIRED STRUCTURE:
- BootScene: generates ALL textures then transitions to TitleScene (or PlayScene)
- One scene per spec.scene_flow entry — each with complete create() AND update()
- CONFIG object at the top with EVERY value from spec.balance_tables (no placeholders)
- Full core loop: spawn, collision, scoring, difficulty ramp, death, restart
- If spec.example_chunks is non-empty: implement a chunk sequencer that cycles them

PROCEDURAL VISUALS — no plain colored boxes:
Every entity texture must layer at least 4-5 distinct drawing operations in BootScene.
Combine fillRect, fillCircle, fillTriangle, strokeRect, strokeCircle, and lineTo arcs.
Use a thematic palette per entity (not random colors). Add outlines and accent details.
Background: at least 2 scrolling tileSprite layers at different speeds.
Player must have a subtle idle animation: a looping tween on scale or y position.

AUDIO — Web Audio API (mandatory):
Create AudioContext on the first pointerdown or keydown event (autoplay policy).
Write a playTone(freq, waveType, duration, volume) helper using OscillatorNode + GainNode.
Minimum sounds: action (jump/fire), pickup/collect, hit/death.

CONTROLS — implement these FIRST, before any other system in PlayScene.create():
Read spec.technical_notes for the input scheme. Wire every listed input to its \
handler at the TOP of create(), before arrays, pools, or spawners. \
If the spec says "left/right arrow keys", create this.cursors and handle LEFT/RIGHT. \
If the spec says "swipe", set up pointerdown + pointermove delta handlers. \
If the spec says "tap = jump, swipe left/right = lane switch", implement BOTH. \
A control that is "optional" or "if enabled" must still be implemented and enabled. \
Disabling a core movement mechanic (lane_switch_enabled: false, etc.) is forbidden.

INITIALIZATION ORDER RULE — in every scene's create():
Declare ALL arrays and objects (this.activeX = [], this.pool = new Pool(), etc.) \
BEFORE calling any method that uses them. Never call spawnX(), initX(), or startX() \
before the arrays/objects those methods push into are initialized.

TECHNICAL RULES:
- dt = delta / 1000 in every update(). Never use deltaTime or elapsed.
- Zero external files. All sprites = generateTexture(). All audio = Web Audio API.
- Every scene = class extending Phaser.Scene with super('SceneName') constructor.
- Phaser.Game config: type Phaser.AUTO, backgroundColor set, arcade physics enabled.
- NEVER call Canvas 2D context methods on a Phaser Graphics object — they don't exist \
and throw TypeError at runtime. Banned: g.save(), g.restore(), g.translate(), \
g.rotate(), g.quadraticCurveTo(), g.bezierCurveTo(), g.setTransform(), g.clip(). \
Use only Phaser Graphics API: fillRect, fillCircle, fillEllipse, fillTriangle, \
strokeRect, strokeCircle, arc, moveTo, lineTo, fillPath, strokePath. \
Bake all offsets directly into x/y arguments — no matrix transforms.
- Output ONLY raw HTML. No markdown fences. No explanations.
- Start with <!DOCTYPE html> and end with </html>. Nothing else.
"""


CODE_PASS2_PROMPT = """\
Expand this Phaser 3 game into a production-quality implementation.

Game: **{title}** | Genre: **{genre}**

Spec:
{spec_json}

Current game (Pass 1):
```html
{previous_code}
```

PASS 2 — SYSTEMS
Deepen and complete every gameplay system. Do not remove any existing code — extend it.

SPAWNING AND POOLING:
If spec.example_chunks is non-empty, implement a real chunk sequencer: maintain a \
chunk index, advance it on each spawn, cycle through the spec chunks in order.
Otherwise: implement at least 3 distinct spawn formations or obstacle patterns.
Use object pooling — group.get() / setActive(true) / setVisible(true) — instead of \
repeated create() calls that spike GC.

DIFFICULTY PROGRESSION:
Implement a continuous ramp from spec.balance_tables: speed and spawn rate increase \
every N seconds. Define at least 3 distinct phases. Show a brief visual indicator \
(flash or text) when a phase changes.

SCORING AND PERSISTENCE:
Persist the best score in localStorage. Show it on the HUD and game-over screen.
When the score increases, spawn a floating "+N" text that rises and fades out using \
a tween (scale 1→0, y -= 40, alpha 1→0 over 700ms).
Add a combo multiplier if the GDD mentions combos; otherwise add a distance bonus.

HITBOXES:
Call setSize() and setOffset() on every physics body.
Use 60-70% of visual sprite dimensions for hitboxes — forgiving feel beats precision.

PARALLAX BACKGROUND:
Ensure at least 3 tileSprite layers scrolling at different speeds (e.g. 0.2x, 0.5x, 1x).

HUD:
Display score, best score, and any lives/health from the spec.
Anchor all HUD elements to the camera viewport (setScrollFactor(0)), not world coords.

CLEANUP:
Destroy or pool-return any object that moves off-screen (x < -128 or y > height + 64).
On game-over → restart: reset all counters, clear all groups, start scene fresh.

Output the COMPLETE updated HTML file — not a diff, the entire file.
Same rules: dt only, zero external files, generateTexture, Web Audio, raw HTML only. \
Never use Canvas 2D methods (save/restore/translate/rotate/quadraticCurveTo/bezierCurveTo) \
on Phaser Graphics — use only Phaser Graphics API and bake offsets into coords.
"""


CODE_PASS3_PROMPT = """\
Add juice, polish and game feel to this Phaser 3 game.

Game: **{title}** | Genre: **{genre}**

GDD juice list — implement EVERY item:
{juice_list}

Current game (Pass 2):
```html
{previous_code}
```

PASS 3 — JUICE
Implement every item in the juice list above, plus all of the following baseline polish.

SCREEN EFFECTS:
- Death/hit: this.cameras.main.shake(300, 0.02) + a brief red overlay tween (alpha 0→0.4→0)
- Milestone or phase change: this.cameras.main.flash(200, 255, 255, 255, true)
- Near-miss or close dodge: subtle shake(80, 0.004)

PARTICLES:
- Death: Phaser particle emitter — 20-30 particles, radial burst, 800ms lifespan, gravity
- Pickup or collect: 8-10 particles, upward arc, color matching the pickup
- Ambient: one persistent emitter tied to the player (dust trail, sparks, or bubbles)

TWEENS ON EVERY STATE CHANGE:
- Score increment: scale text 1→1.35→1, duration 200ms, ease 'Back.easeOut'
- Entity spawn: scale 0→1, ease 'Elastic.easeOut', duration 400ms
- Player death: scale 1→0 combined with 360-degree rotation over 500ms before game-over
- All scene transitions: this.cameras.main.fadeOut(400) on exit, fadeIn(400) on enter

HIT FREEZE (critical for game feel — do not skip):
On any damaging collision: this.physics.world.pause() for 50ms then resume.
Flash the hit entity: setTint(0xff4444), then tween tint back to 0xffffff over 200ms.

AUDIO POLISH:
- Pitch variation: multiply frequency by (0.88 + Math.random() * 0.24) on each playTone call
- Background music: a simple looping pattern via OscillatorNode. Starts on first input, \
pauses on death, resumes on retry.
- Death sound: linearRampToValueAtTime from 800 Hz to 80 Hz over 400ms.
- Milestone sound: ascending 3-note arpeggio (e.g. 440, 554, 659 Hz played 80ms apart).

TITLE SCREEN POLISH:
- Title text: floating sine-wave via a looping yoyo tween on y (±8px, duration 1800ms)
- "Tap to Play" text: pulse alpha 1→0.25→1 in a loop, duration 900ms
- Background parallax layers must already be scrolling on the title screen

GAME OVER SCREEN:
- Show score and best score prominently side by side
- If a new high score was set: display a "New Best!" banner with a scale-in tween
- Retry button: scale tween on pointerover (1→1.1) and pointerout (1.1→1)

Output the COMPLETE final HTML file — the entire file, not a patch.
Same rules: dt only, zero external files, generateTexture, Web Audio, raw HTML only. \
Never use Canvas 2D methods (save/restore/translate/rotate/quadraticCurveTo/bezierCurveTo) \
on Phaser Graphics — use only Phaser Graphics API and bake offsets into coords.
"""


REWORK_CODE_PROMPT = """\
Fix this Phaser 3 game based on reviewer feedback. Output the COMPLETE corrected file.

Game: **{title}** | Genre: **{genre}**

Spec:
{spec_json}

Previous code:
```html
{previous_code}
```

Review — Score {score}/10
Strengths (preserve these): {strengths}
MUST FIX (every item is blocking): {issues}
Nice to have: {suggestions}

Address every blocking issue precisely. Do not regress any working system.
Preserve all juice and polish that was already present in the code.
Same rules: dt = delta/1000 only, zero external files, generateTexture for all sprites, \
Web Audio for all sounds, every scene extends Phaser.Scene, raw HTML from \
<!DOCTYPE html> to </html>. \
Never use Canvas 2D methods (save/restore/translate/rotate/quadraticCurveTo/bezierCurveTo) \
on Phaser Graphics — use only Phaser Graphics API and bake offsets into coords.
"""


def generate_code(state: PipelineState) -> PipelineState:
    llm = ChatOpenAI(
        model=LLM_MODEL,
        temperature=0.3,
        max_tokens=_max_tokens(LLM_MODEL, 32_768),
    )

    gdd = state["gdd"]
    impl_spec = state["impl_spec"]
    gdd_json = gdd.model_dump_json()
    spec_json = impl_spec.model_dump_json()
    attempt = state.get("code_attempt", 0) + 1
    review = state.get("code_review")

    if review and not review.passed:
        # Targeted rework: reviewer identified specific issues — fix them precisely.
        html = _run_code_pass(llm, REWORK_CODE_PROMPT.format(
            title=gdd.title,
            genre=state["genre"],
            spec_json=spec_json,
            previous_code=state["code"].html_code,
            score=review.score,
            strengths="; ".join(review.strengths),
            issues="; ".join(review.issues),
            suggestions="; ".join(review.suggestions),
        ))
    else:
        # First attempt — three-pass generation: foundation → systems → juice.
        juice_list = "\n".join(f"  - {j}" for j in gdd.juice_list)

        print(f"  [generate_code] Pass 1/3 (foundation) ...")
        code1 = _run_code_pass(llm, CODE_PASS1_PROMPT.format(
            title=gdd.title, genre=state["genre"],
            gdd_json=gdd_json, spec_json=spec_json,
        ))
        output.save_text("04_code", "game_pass1.html", code1, attempt=attempt)
        issues1 = check_html_game(code1)

        if len(issues1) > 5:
            # Pass 1 catastrophically broken — surface it for the review cycle to diagnose.
            html = code1
        else:
            print(f"  [generate_code] Pass 2/3 (systems) ...")
            code2 = _run_code_pass(llm, CODE_PASS2_PROMPT.format(
                title=gdd.title, genre=state["genre"],
                spec_json=spec_json, previous_code=code1,
            ))
            output.save_text("04_code", "game_pass2.html", code2, attempt=attempt)
            issues2 = check_html_game(code2)
            best2 = code2 if len(issues2) <= len(issues1) else code1

            print(f"  [generate_code] Pass 3/3 (juice) ...")
            code3 = _run_code_pass(llm, CODE_PASS3_PROMPT.format(
                title=gdd.title, genre=state["genre"],
                juice_list=juice_list, previous_code=best2,
            ))
            output.save_text("04_code", "game_pass3.html", code3, attempt=attempt)
            issues3 = check_html_game(code3)
            html = code3 if len(issues3) <= len(issues2) else best2

    game = GeneratedGame(
        html_code=html,
        implementation_notes=["Multi-pass generation (foundation → systems → juice)."],
    )

    html_path = output.save_text("04_code", "game.html", game.html_code, attempt=attempt)
    output.save(
        "04_code", "notes.json",
        {"implementation_notes": game.implementation_notes},
        attempt=attempt,
    )
    print(f"  [generate_code] Attempt {attempt} → {output.rel(html_path)}")

    return {"code": game, "code_attempt": attempt}


# ---------------------------------------------------------------------------
# Node: review_code
# ---------------------------------------------------------------------------
CODE_REVIEW_PROMPT = """\
Review this Phaser 3 game against its implementation spec.

Game: **{title}** | Genre: **{genre}**

Spec:
{spec_json}

Code:
```html
{code}
```

Score 1-10 (pass >= 7). Weighted criteria:

- **Runtime correctness** (4x): Does the game run without errors? Any undefined \
variable, missing method, broken game loop, or unhandled crash = score <= 4. \
Name the exact scene/function and the error or missing reference.

- **Core loop completeness** (3x): Can a player start, play, die, and restart \
without getting stuck? Is every mechanic from the spec implemented — not stubbed \
or omitted? Name any mechanic that is missing or non-functional.

- **Game feel and juice** (2x): Does it have screen shake on death, particle effects \
on pickups/death, tween animations on score and entities, audio feedback, and a \
parallax background? List specifically what IS present and what is MISSING.

- **Spec fidelity** (1x): Do balance values, entity properties, and state machine \
transitions match the spec? Note any significant deviations.

CONTROLS AUDIT (required — treat failures as runtime correctness bugs):
For every input listed in spec.technical_notes, answer: what is the exact Phaser \
event/method that handles it, and what does it trigger? If any listed control has \
no handler, or is present but disabled (e.g. a flag set to false), treat it as a \
blocking bug. Example: "spec says left/right arrow keys → lane switch; code has \
cursors.left but no lane switch handler — BLOCKER."

INITIALIZATION ORDER (flag if violated):
Check that PlayScene.create() (or equivalent) declares all arrays (activeX = [], \
pools, groups) BEFORE calling any method that pushes into them. If spawnX() or \
initX() is called before the arrays it uses are initialized, name it as a blocker.

Scoring guide:
- 9-10: Excellent. Ships as-is.
- 7-8: Good. Minor gaps, fully playable.
- 5-6: Playable but missing key systems or has significant bugs. List up to 5 blockers.
- 3-4: Broken core loop or runtime errors prevent play.
- 1-2: Does not run at all.

Be precise: name the scene, the method, the expected behavior vs actual.
List at most 5 blocking issues and 5 suggestions.
"""


def review_code(state: PipelineState) -> PipelineState:
    """Review the generated game code against the implementation spec.

    Runs automated validation first — if critical issues are found,
    skips the LLM call entirely and returns a synthetic failing review.
    """
    code = state["code"].html_code
    attempt = state.get("code_attempt", 1)    

    # ── Automated validation gate (free, no tokens) ───────────────────
    validation_issues = check_html_game(code)
    if len(validation_issues) > 5:
        # fail fast, skip LLM review, return directly
        return {"code_review": CodeReview(
            passed=False, score=2,
            strengths=[], issues=validation_issues, suggestions=[]
        )}
    if validation_issues:
        review = CodeReview(
            passed=False,
            score=3,
            strengths=["Skipped LLM review — fix validation errors first."],
            issues=validation_issues,
            suggestions=[],
        )
        path = output.save(
            "04_code", "review.json", review.model_dump(), attempt=attempt
        )
        print(f"  [review_code] VALIDATION FAILED ({len(validation_issues)} issue(s)) → {output.rel(path)}")
        return {"code_review": review}

    # ── LLM review (code passed basic checks) ────────────────────────
    llm = ChatOpenAI(
        model=REVIEW_MODEL,
        temperature=0.3,
        max_tokens=1024,
    )

    structured_llm = llm.with_structured_output(CodeReview, method="function_calling")

    spec_json = state["impl_spec"].model_dump_json()

    review = invoke_with_retry(
        structured_llm,
        CODE_REVIEW_PROMPT.format(
            title=state["gdd"].title,
            genre=state["genre"],
            spec_json=spec_json,
            code=code,
        ),
    )

    status = "passed" if review.passed and review.score >= 7 else "needs rework"
    path = output.save(
        "04_code", "review.json", review.model_dump(), attempt=attempt
    )
    print(f"  [review_code] Score {review.score}/10 ({status}) → {output.rel(path)}")

    return {"code_review": review}


def should_rework_code(state: PipelineState) -> str:
    """Conditional edge: decide whether to rework the code or finish."""
    review = state["code_review"]
    attempt = state.get("code_attempt", 1)

    if review.passed and review.score >= 7:
        return END

    if attempt >= MAX_CODE_ATTEMPTS:
        # Avoid infinite loops — ship what we have
        return END

    return "generate_code"


# ---------------------------------------------------------------------------
# Graph wiring
# ---------------------------------------------------------------------------
def build_graph(checkpointer=None):
    """Build and compile the game design pipeline graph.

    Flow:
        START → research_genre → generate_gdd → review_gdd ─┬─ (fail) → generate_gdd
                                                             └─ (pass) → human_review_gdd
                                                                           │
                            ┌── (reject) ──────────────────────────────────┘
                            ↓                                  │
                       generate_gdd ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─    │
                                                               └─ (approve)
                                                                     ↓
        generate_impl_spec → review_impl_spec ─┬─ (fail) → human_review_impl_spec
                                               └─ (pass) → generate_code
                                                                  │
                            ┌── (fix) ───────────────────────────┤
                            ↓                                      └─ (approve)
                       generate_impl_spec ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
                                                               ↓
        generate_code → review_code ─┬─ (fail) → generate_code
                                     └─ (pass) → END

    Args:
        checkpointer: LangGraph checkpointer for HITL interrupt persistence.
                      Required for human_review_gdd to work.
    """
    builder = StateGraph(PipelineState)

    # Nodes
    builder.add_node("research_genre", research_genre)
    builder.add_node("generate_gdd", generate_gdd)
    builder.add_node("review_gdd", review_gdd)
    builder.add_node("human_review_gdd", human_review_gdd)
    builder.add_node("generate_impl_spec", generate_impl_spec)
    builder.add_node("review_impl_spec", review_impl_spec)
    builder.add_node("human_review_impl_spec", human_review_impl_spec)

    # Edges — GDD cycle
    builder.add_edge(START, "research_genre")
    builder.add_edge("research_genre", "generate_gdd")
    builder.add_edge("generate_gdd", "review_gdd")
    builder.add_conditional_edges("review_gdd", should_rework_gdd)
    builder.add_conditional_edges(
        "human_review_gdd", should_proceed_after_human_review
    )

    # Edges — Impl spec cycle
    builder.add_edge("generate_impl_spec", "review_impl_spec")
    builder.add_conditional_edges("review_impl_spec", should_rework_impl_spec)
    builder.add_conditional_edges(
        "human_review_impl_spec", should_proceed_after_impl_review
    )

    # Nodes — Code gen cycle
    builder.add_node("generate_code", generate_code)
    builder.add_node("review_code", review_code)

    # Edges — Code gen cycle
    builder.add_edge("generate_code", "review_code")
    builder.add_conditional_edges("review_code", should_rework_code)

    return builder.compile(checkpointer=checkpointer)
