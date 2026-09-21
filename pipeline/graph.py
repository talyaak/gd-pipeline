"""AI Game Design Pipeline — LangGraph graph with Cycle X + HITL.

Step 1: Genre Research — structured analysis of a game genre.
Step 2: GDD Generation — Cycle X auto-review + HITL human approval gate.
Step 3: Implementation Spec — Cycle X auto-review for technical completeness.
Step 4: Code Generation — produce a single-file HTML5 browser game.
Step 5: Code Review — Cycle X auto-review for playability and spec fidelity.
Step 6: Vision Verification — Screenshot + vision model review for visual bugs.
Step 7: Playtest Agent — Headless browser plays game, extracts metrics.

Cycle X pattern: Generate -> Review -> Fix -> Repeat until quality threshold met.
HITL: Human-in-the-loop interrupt between GDD approval and impl spec generation.
"""

import os
from dotenv import load_dotenv
from typing import TypedDict

# Load .env for OpenRouter API key
load_dotenv()

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from pipeline import output
from pipeline.retry import invoke_with_retry
from pipeline.schemas import (
    AssetEntry,
    BalanceParam,
    BalanceTable,
    CodeReview,
    EntityDef,
    GameDesignDocument,
    GddReview,
    GeneratedGame,
    GameState,
    GenreAnalysis,
    ImplSpecReview,
    ImplementationSpec,
    PropertyDef,
)
from pipeline.validate import check_html_game

# ─── Model Configuration: OpenRouter Free Tier ──────────────────────────────
# Set OPENROUTER_API_KEY in .env — get free key at openrouter.ai
# Models: https://openrouter.ai/models

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Generation: best free coding model with vision + 1M context
GEN_MODEL = os.getenv("GEN_MODEL", "openrouter/free")
# Review: fast, cheap, good reasoning
REVIEW_MODEL = os.getenv("REVIEW_MODEL", "openrouter/free")
# Vision: same as gen model (supports vision)
VISION_MODEL = os.getenv("VISION_MODEL", "openrouter/free")

# Output token limits for OpenRouter models
_MODEL_OUTPUT_LIMITS: dict[str, int] = {
    "meta-llama/llama-3.1-8b-instruct":  4_096,
    "meta-llama/llama-3.1-8b-instruct:free":  4_096,
    "meta-llama/llama-3.1-70b-instruct":  4_096,
    "meta-llama/llama-3.1-405b-instruct":  4_096,
    "qwen/qwen-2.5-32b-instruct:free":   8_192,
    "qwen/qwen-2.5-72b-instruct:free":   8_192,
    "deepseek/deepseek-chat:free":       8_192,
    "deepseek/deepseek-chat":       8_192,
    "mistralai/mistral-7b-instruct:free": 4_096,
    "mistralai/mistral-small-3.1-24b-instruct:free": 4_096,
    "google/gemini-2.0-flash-exp:free":  8_192,
    "google/gemini-1.5-flash:free":      8_192,
    "nvidia/nemotron-3-ultra:free":      4_096,
}

def _max_tokens(model: str, want: int) -> int:
    """Cap *want* to the model's output-token limit."""
    return min(want, _MODEL_OUTPUT_LIMITS.get(model, 8_192))


def _make_llm(model: str, temperature: float, max_tokens: int) -> ChatOpenAI:
    """Create ChatOpenAI configured for OpenRouter."""
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        base_url=OPENROUTER_BASE_URL,
        api_key=os.getenv("OPENROUTER_API_KEY"),
        default_headers={
            "HTTP-Referer": "https://github.com/talyaak/gd-pipeline",
            "X-Title": "gd-pipeline",
        },
    )

MAX_GDD_ATTEMPTS       = 3
MAX_IMPL_SPEC_ATTEMPTS = 2
MAX_CODE_ATTEMPTS      = 3
MAX_VISION_ATTEMPTS    = 2
MAX_PLAYTEST_ATTEMPTS  = 2


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
    # New: Vision verification
    vision_review: CodeReview | None
    vision_attempt: int
    vision_screenshot_path: str | None
    # New: Playtest agent
    playtest_results: dict | None
    playtest_review: CodeReview | None
    playtest_attempt: int


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
    llm = _make_llm(REVIEW_MODEL, temperature=0.3, max_tokens=_max_tokens(REVIEW_MODEL, 2048))

    structured_llm = llm.with_structured_output(GenreAnalysis, method="function_calling")

    analysis = invoke_with_retry(
        structured_llm, RESEARCH_PROMPT.format(genre=state["genre"])
    )

    path = output.save("01_genre_research", "analysis.json", analysis.model_dump())
    print(f"  [research_genre] Done -> {output.rel(path)}")

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
    llm = _make_llm(GEN_MODEL, temperature=0.7, max_tokens=_max_tokens(GEN_MODEL, 32_768))

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

    # Fallback: if LLM returns None, create a basic GDD from analysis
    if gdd is None:
        analysis = state["analysis"]
        gdd = GameDesignDocument(
            title=f"{analysis.genre.title()} Rush",
            one_liner=f"Fast-paced {analysis.genre} with lane-switching, jumps, and neon juice.",
            core_loop=[
                "Auto-run forward at increasing speed",
                "Tap left/right or swipe to switch lanes and dodge obstacles",
                "Jump over low obstacles, slide under high ones",
                "Collect orbs for score and temporary speed boost",
                "Survive as long as possible — speed increases every phase"
            ],
            controls="Tap left half of screen / Left arrow = move left lane. Tap right half / Right arrow = move right lane. Tap anywhere / Space / Up arrow = jump. Swipe down / Down arrow = slide.",
            visual_style="Minimalist neon pixel-art on deep black. Player: glowing 2-block sprite with trail. Obstacles: sharp geometric shapes with glow. Orbs: pulsing circles. Background: 3-layer parallax starfield. All procedural.",
            mechanics=[
                "Lane switching (3 lanes) with buffered input",
                "Variable-height jump with coyote time (0.08s) and jump buffer (0.12s)",
                "Slide with faster gravity for quick drops",
                "Orb collection with combo multiplier (chain within 2s)",
                "Phase-based difficulty: speed +10% every 15s, telegraph 2s before"
            ],
            progression_system="Distance-based high score with localStorage persistence. Daily challenge seed. Unlock neon skins at 10k/50k/100k distance. Power-ups: Magnet (attract orbs), Shield (1 hit), Slow-Mo (2s).",
            juice_list=[
                "0.05s hit-freeze on collision + 12-particle radial burst",
                "Screen shake 300ms/0.02 on death, 80ms/0.004 on near-miss",
                "Landing squash: scaleY 0.85 for 80ms, ease Back.easeOut",
                "Coyote dust puff at ledge edge when jumping off",
                "Orb collect: 8-particle upward arc + pitch-rising chime",
                "Phase change: camera flash(200ms) + speed indicator text",
                "Combo counter: scale 1->1.5->1, color shifts white->gold->rainbow",
                "Background music: adaptive layers, pitch rises with speed"
            ],
            mvp_scope=[
                "Auto-run with 3-lane switching (tap/swipe/arrows)",
                "Jump (coyote + buffer) and slide mechanics",
                "Obstacle spawning with fair gaps (min 2 clear lanes)",
                "Orb collection with combo system",
                "3 HP health with invincibility frames on hit",
                "Phase progression with 2s telegraph",
                "HUD: score, best, health hearts, combo counter",
                "Procedural neon graphics + Web Audio SFX"
            ],
            post_mvp=[
                "Daily challenge with fixed seed",
                "Neon skin gallery (8 unlockable palettes)",
                "Weekly themed events",
                "Leaderboards (local + daily top 50)",
                "Magnet/Shield/Slow-Mo power-ups"
            ],
            gamification=None  # Will be populated by fallback if needed
        )

    path = output.save("02_gdd", "gdd.json", gdd.model_dump(), attempt=attempt)
    print(f"  [generate_gdd] Attempt {attempt} -> {output.rel(path)}")

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
movement inputs (e.g. 3 lanes -> left/right inputs). A multi-lane game with \
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
    llm = _make_llm(REVIEW_MODEL, temperature=0.3, max_tokens=_max_tokens(REVIEW_MODEL, 512))

    structured_llm = llm.with_structured_output(GddReview, method="function_calling")

    gdd_json = state["gdd"].model_dump_json()

    review = invoke_with_retry(
        structured_llm,
        REVIEW_GDD_PROMPT.format(genre=state["genre"], gdd_json=gdd_json),
    )

    # Fallback: if LLM returns None (model doesn't support function calling),
    # create a basic review from validation heuristics
    if review is None:
        gdd = state["gdd"]
        issues = []
        if not gdd.core_loop or len(gdd.core_loop) < 3:
            issues.append("Core loop has fewer than 3 steps")
        if not gdd.controls or len(gdd.controls) < 20:
            issues.append("Controls description too brief")
        if not gdd.mechanics or len(gdd.mechanics) < 4:
            issues.append("Fewer than 4 mechanics defined")
        if not gdd.juice_list or len(gdd.juice_list) < 5:
            issues.append("Juice list has fewer than 5 items")
        if not gdd.gamification:
            issues.append("Missing gamification spec (Octalysis, DDA, retention)")

        score = max(4, 10 - len(issues) * 2)
        review = GddReview(
            passed=score >= 7,
            score=score,
            strengths=["GDD generated successfully"],
            issues=issues,
            suggestions=["Add more specific physics parameters", "Detail collision/hitbox specs"]
        )

    attempt = state.get("gdd_attempt", 1)
    status = "passed" if review.passed and review.score >= 7 else "needs rework"
    path = output.save("02_gdd", "review.json", review.model_dump(), attempt=attempt)
    print(f"  [review_gdd] Score {review.score}/10 ({status}) -> {output.rel(path)}")

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
    """Conditional edge: human approved -> impl spec, rejected -> rework GDD."""
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
lifecycle: load -> play -> die -> retry.

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
    llm = _make_llm(GEN_MODEL, temperature=0.3, max_tokens=_max_tokens(GEN_MODEL, 32_768))

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

    # Fallback: if LLM returns None, derive a minimal spec from the GDD so the
    # code-generation stage always has something concrete to work from.
    if impl_spec is None:
        gdd = state["gdd"]
        impl_spec = ImplementationSpec(
            entities=[
                EntityDef(
                    name="Player",
                    properties=[
                        PropertyDef(name="speed", type_description="number — pixels/sec, default 300"),
                        PropertyDef(name="alive", type_description="boolean — default true"),
                    ],
                    behavior="Moves per controls in the GDD; collides with hazards and collects pickups.",
                )
            ],
            state_machine=[
                GameState(
                    name="Loading", description="Boot scene, generate assets.",
                    transitions=["assets_ready → Playing"],
                ),
                GameState(
                    name="Playing", description="Core loop from the GDD.",
                    transitions=["player_dies → GameOver"],
                ),
                GameState(
                    name="GameOver", description="Show score, tap to restart.",
                    transitions=["player_taps → Playing"],
                ),
            ],
            balance_tables=[
                BalanceTable(
                    category="Player",
                    params=[BalanceParam(name="player_speed", value="300 px/s — fast enough to dodge, slow enough to plan")],
                )
            ],
            scene_flow=["TitleScreen — logo + tap to start", "Playing — core loop", "GameOver — score + tap to retry"],
            asset_manifest=[
                AssetEntry(name="spr_player", asset_type="sprite", description="Player sprite per the GDD visual style."),
                AssetEntry(name="sfx_hit", asset_type="sound", description="Collision sound effect."),
            ],
            technical_notes=[f"Derive all mechanics from the approved GDD '{gdd.title}'; Phaser 3, single-file HTML."],
        )

    path = output.save(
        "03_impl_spec", "impl_spec.json", impl_spec.model_dump(), attempt=attempt
    )
    print(f"  [generate_impl_spec] Attempt {attempt} -> {output.rel(path)}")

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
- **State machine** (weight: 1x): Load -> Play -> GameOver -> Retry covered. \
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
    llm = _make_llm(REVIEW_MODEL, temperature=0.3, max_tokens=_max_tokens(REVIEW_MODEL, 512))

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

    # Fallback: if LLM returns None, create basic review from validation
    if review is None:
        spec = state["impl_spec"]
        issues = []
        if not spec.entities or len(spec.entities) < 3:
            issues.append("Fewer than 3 entities defined")
        if not spec.balance_tables or len(spec.balance_tables) < 2:
            issues.append("Missing balance tables")
        if not spec.asset_manifest or len(spec.asset_manifest) < 5:
            issues.append("Asset manifest incomplete (<5 items)")
        if not spec.state_machine or len(spec.state_machine) < 3:
            issues.append("State machine missing states (need Loading, Playing, GameOver)")
        if not spec.technical_notes:
            issues.append("No technical notes for implementation guidance")

        score = max(4, 10 - len(issues) * 2)
        review = ImplSpecReview(
            passed=score >= 7,
            score=score,
            strengths=["Implementation spec generated"],
            issues=issues,
            suggestions=["Add hitbox sizes to entities", "Detail spawn patterns in example_chunks"]
        )

    attempt = state.get("impl_spec_attempt", 1)
    status = "passed" if review.passed and review.score >= 7 else "needs rework"
    path = output.save(
        "03_impl_spec", "review.json", review.model_dump(), attempt=attempt
    )
    print(f"  [review_impl_spec] Score {review.score}/10 ({status}) -> {output.rel(path)}")

    return {"impl_spec_review": review}


def should_rework_impl_spec(state: PipelineState) -> str:
    """Conditional edge: pass -> code gen, fail -> human review (no auto-retry loop)."""
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
    """Conditional edge: human approved -> code gen, rejected -> rework impl spec."""
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

PHYSICS FEEL — REQUIRED (tune these in CONFIG, do not hardcode):
- gravity: 5200 px/s2 (adjust for genre)
- jumpVelocity: -1750 px/s (negative = up)
- jumpBuffer: 0.12s (queue jump if pressed within this before landing)
- coyoteTime: 0.08s (allow jump within this after leaving ground)
- variableJump: hold jump key for higher jump (min 60% velocity at release)
- airControl: 0.6 (horizontal acceleration multiplier while airborne)
- slideHoldThreshold: 0.10s (hold down to slide vs tap for drop)
- slideGravityMultiplier: 2.5 (faster fall during slide)

CONTROLS — implement these FIRST, before any other system in PlayScene.create():
Read spec.technical_notes for the input scheme. Wire every listed input to its \
handler at the TOP of create(), before arrays, pools, or spawners. \
If the spec says "left/right arrow keys", create this.cursors and handle LEFT/RIGHT. \
If the spec says "swipe", set up pointerdown + pointermove delta handlers. \
If the spec says "tap = jump, swipe left/right = lane switch", implement BOTH. \
A control that is "optional" or "if enabled" must still be implemented and enabled. \
Disabling a core movement mechanic (lane_switch_enabled: false, etc.) is forbidden.

INPUT BUFFERING (critical for responsiveness):
- Lane switch inputs buffered for 0.15s — if player swipes during jump, execute on land
- Jump input buffered via jumpBuffer above
- Clear buffers on death/restart
- Touch: 30px minimum swipe distance, 300ms max swipe duration
- Keyboard: prevent key repeat from triggering multiple jumps

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

FAIR SPAWNING (critical — no unfair deaths):
- Minimum safe gap between obstacles: ensure at least 2 adjacent lanes are clear
- Obstacle spawn X must be OFF-SCREEN RIGHT (canvas.width + 100), never in viewport
- Use spec.balance_tables spawn_rate, NOT Math.random() with wall-clock timers
- Spawner MUST use dt from game loop, not setInterval (which desyncs on tab blur)
- Phase transitions: 2-second warning flash before speed/spawn changes take effect
- Difficulty ramp caps at CONFIG.maxSpeedMultiplier from balance_tables

DIFFICULTY PROGRESSION:
Implement a continuous ramp from spec.balance_tables: speed and spawn rate increase \
every N seconds. Define at least 3 distinct phases. Show a brief visual indicator \
(flash or text) when a phase changes. PHASE CHANGE MUST TELEGRAPH 2s BEFORE.

SCORING AND PERSISTENCE:
Persist the best score in localStorage. Show it on the HUD and game-over screen.
When the score increases, spawn a floating "+N" text that rises and fades out using \
a tween (scale 1->0, y -= 40, alpha 1->0 over 700ms).
Add a combo multiplier if the GDD mentions combos; otherwise add a distance bonus.
DISPLAY COMBO COUNTER ON HUD (top-center, fades after 2s of no combo)

HITBOXES & COLLISION FORGIVENESS:
Call setSize() and setOffset() on every physics body.
Use 60-70% of visual sprite dimensions for hitboxes — forgiving feel beats precision.
ON DAMAGING COLLISION:
- Grant 0.5s invincibility frames (player.setTint(0xffffff), alpha pulse 0.5->1)
- Knockback: player pushed back 50px, velocity.y = -300 (small hop)
- Screen shake(200, 0.015) + hit freeze(50ms) — NOT instant death
- Health system: 3 HP, render hearts on HUD, only die at 0 HP
- Invincibility frames: ignore collisions while flashing

PARALLAX BACKGROUND:
Ensure at least 3 tileSprite layers scrolling at different speeds (e.g. 0.2x, 0.5x, 1x).

HUD:
Display score, best score, and any lives/health from the spec.
Anchor all HUD elements to the camera viewport (setScrollFactor(0)), not world coords.
Score top-left, best score top-right, health hearts top-center.

CLEANUP:
Destroy or pool-return any object that moves off-screen (x < -128 or y > height + 64).
On game-over -> restart: reset all counters, clear all groups, start scene fresh.

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
- Death/hit: this.cameras.main.shake(300, 0.02) + a brief red overlay tween (alpha 0->0.4->0)
- Milestone or phase change: this.cameras.main.flash(200, 255, 255, 255, true)
- Near-miss or close dodge: subtle shake(80, 0.004) + white flash(50ms)
- Coyote time visual: dust puff at player feet when jumping off ledge edge
- Landing squash: scaleY 0.85 for 80ms, ease 'Back.easeOut' on ground contact

PARTICLES:
- Death: Phaser particle emitter — 20-30 particles, radial burst, 800ms lifespan, gravity
- Pickup or collect: 8-10 particles, upward arc, color matching the pickup
- Ambient: one persistent emitter tied to the player (dust trail, sparks, or bubbles)
- Near-miss: 4-6 spark particles at dodge point, 300ms lifespan

TWEENS ON EVERY STATE CHANGE:
- Score increment: scale text 1->1.35->1, duration 200ms, ease 'Back.easeOut'
- Entity spawn: scale 0->1, ease 'Elastic.easeOut', duration 400ms
- Player death: scale 1->0 combined with 360-degree rotation over 500ms before game-over
- All scene transitions: this.cameras.main.fadeOut(400) on exit, fadeIn(400) on enter
- Health heart loss: scale 1->0.5->1, red tint flash, duration 300ms
- Combo counter: scale 1->1.5->1 on increment, color shift (white->gold->rainbow)

HIT FREEZE (critical for game feel — do not skip):
On any damaging collision: this.physics.world.pause() for 50ms then resume.
Flash the hit entity: setTint(0xff4444), then tween tint back to 0xffffff over 200ms.
INVINCIBILITY: 0.5s alpha pulse (0.5<->1) after hit, ignore collisions during.

AUDIO POLISH:
- Pitch variation: multiply frequency by (0.88 + Math.random() * 0.24) on each playTone call
- Background music: a simple looping pattern via OscillatorNode. Starts on first input, \
pauses on death, resumes on retry.
- Death sound: linearRampToValueAtTime from 800 Hz to 80 Hz over 400ms.
- Milestone sound: ascending 3-note arpeggio (e.g. 440, 554, 659 Hz played 80ms apart).
- Near-miss sound: 700 Hz sine, 50ms, low volume (0.08)
- Jump sound: pitch varies with hold duration (short=high, long=low)

TITLE SCREEN POLISH:
- Title text: floating sine-wave via a looping yoyo tween on y (±8px, duration 1800ms)
- "Tap to Play" text: pulse alpha 1->0.25->1 in a loop, duration 900ms
- Background parallax layers must already be scrolling on the title screen
- High score display: "BEST: {{score}}" bottom-center, subtle pulse

GAME OVER SCREEN:
- Show score and best score prominently side by side
- If a new high score was set: display a "New Best!" banner with a scale-in tween
- Retry button: scale tween on pointerover (1->1.1) and pointerout (1.1->1)
- Death recap: "You survived {{time}}s · {{distance}}m · {{combo}}x max combo"

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

CRITICAL PHYSICS FEEL REQUIREMENTS (must be present in CONFIG and implemented):
- jumpBuffer: 0.12s, coyoteTime: 0.08s, variableJump (min 60% velocity), airControl: 0.6
- Input buffering: lane switch buffered 0.15s, touch swipe 30px/300ms thresholds
- Hitboxes: 60-70% of visual size, setSize()/setOffset() on ALL bodies
- On hit: 0.5s invincibility (alpha pulse), knockback 50px + small hop, screen shake(200, 0.015)
- 3 HP health system with hearts on HUD, only die at 0 HP
- Fair spawning: min 2 safe lanes, spawn OFF-SCREEN RIGHT, dt-based spawner (no setInterval)

CRITICAL JUICE REQUIREMENTS:
- Hit freeze 50ms + tint flash red->white 200ms
- Landing squash (scaleY 0.85, 80ms), coyote dust puff
- Near-miss: shake(80, 0.004) + white flash + spark particles
- Combo counter on HUD with scale tween on increment
- Particles: death (20-30 radial), pickup (8-10 up), ambient (trail), near-miss (4-6 sparks)

Address every blocking issue precisely. Do not regress any working system.
Preserve all juice and polish that was already present in the code.
Same rules: dt = delta/1000 only, zero external files, generateTexture for all sprites, \
Web Audio for all sounds, every scene extends Phaser.Scene, raw HTML from \
<!DOCTYPE html> to </html>. \
Never use Canvas 2D methods (save/restore/translate/rotate/quadraticCurveTo/bezierCurveTo) \
on Phaser Graphics — use only Phaser Graphics API and bake offsets into coords.
"""


def generate_code(state: PipelineState) -> PipelineState:
    llm = _make_llm(GEN_MODEL, temperature=0.3, max_tokens=_max_tokens(GEN_MODEL, 32_768))

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
        # First attempt — three-pass generation: foundation -> systems -> juice.
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
        implementation_notes=["Multi-pass generation (foundation -> systems -> juice)."],
    )

    html_path = output.save_text("04_code", "game.html", game.html_code, attempt=attempt)
    output.save(
        "04_code", "notes.json",
        {"implementation_notes": game.implementation_notes},
        attempt=attempt,
    )
    print(f"  [generate_code] Attempt {attempt} -> {output.rel(html_path)}")

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
blocking bug. Example: "spec says left/right arrow keys -> lane switch; code has \
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
        print(f"  [review_code] VALIDATION FAILED ({len(validation_issues)} issue(s)) -> {output.rel(path)}")
        return {"code_review": review}

    # ── LLM review (code passed basic checks) ────────────────────────
    llm = _make_llm(REVIEW_MODEL, temperature=0.3, max_tokens=_max_tokens(REVIEW_MODEL, 1024))

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

    # Fallback: if LLM returns None, create review from validation results
    if review is None:
        issues = validation_issues.copy() if validation_issues else []
        if "No Phaser.Scene class found" in str(issues):
            issues.append("No Scene class - game won't run")
        if "No update() method found" in str(issues):
            issues.append("No update loop - game logic won't execute")
        if "No generateTexture() calls found" in str(issues):
            issues.append("No procedural graphics - will show blank")

        score = max(3, 8 - len(issues))
        review = CodeReview(
            passed=score >= 7,
            score=score,
            strengths=["Code passed basic validation"] if not issues else ["Partial implementation"],
            issues=issues,
            suggestions=["Add coyote time & jump buffer", "Implement 60-70% hitboxes", "Add invincibility frames"]
        )

    status = "passed" if review.passed and review.score >= 7 else "needs rework"
    path = output.save(
        "04_code", "review.json", review.model_dump(), attempt=attempt
    )
    print(f"  [review_code] Score {review.score}/10 ({status}) -> {output.rel(path)}")

    return {"code_review": review}


def should_rework_code(state: PipelineState) -> str:
    """Conditional edge: decide whether to rework the code or proceed to vision verification."""
    review = state["code_review"]
    attempt = state.get("code_attempt", 1)

    if review.passed and review.score >= 7:
        return "verify_vision"

    if attempt >= MAX_CODE_ATTEMPTS:
        # Avoid infinite loops — ship what we have
        return "verify_vision"

    return "generate_code"


# ============================================================
# NEW NODE: Vision Verification — Screenshot + Vision Model
# ============================================================
VISION_VERIFY_PROMPT = """\
You are a visual QA engineer reviewing a Phaser 3 HTML5 game screenshot.

Game: **{title}** | Genre: **{genre}**

Expected (from spec):
- Core loop: {core_loop}
- Key visual elements: {visual_elements}
- Juice items that MUST be visible: {juice_list}

SCREENSHOT ANALYSIS TASK:
Look at the provided screenshot and identify visual bugs. Be ruthless.

CHECKLIST — mark each as PASS/FAIL with evidence:
1. **Game runs** — No black screen, no frozen frame, no console errors visible
2. **Player visible** — Player sprite/character clearly visible, not clipped
3. **HUD readable** — Score, health, lives clearly legible (contrast, font size)
4. **Parallax background** — At least 2 layers scrolling at different speeds
5. **Particles working** — Death/pickup/ambient particles visible
6. **Screen effects** — Shake/flash/hit-freeze evidence (or note if static moment)
7. **UI layout** — No overlapping elements, no off-screen text, no z-index issues
8. **Color/contrast** — Game elements distinguishable, not washed out
9. **Mobile viewport** — No horizontal overflow, fits viewport
10. **Polish level** — Feels "finished" not "prototype" (subjective but important)

SCORING:
- 9-10: Visually polished, all systems visibly working
- 7-8: Minor visual issues, core experience intact
- 5-6: Significant visual bugs affecting playability
- 1-4: Broken visuals, unplayable, or blank screen

List up to 5 specific visual blockers with screenshot evidence (describe what you see).
"""


def verify_vision(state: PipelineState) -> PipelineState:
    """Render game with Playwright, screenshot, and review with vision model."""
    from playwright.async_api import async_playwright
    import asyncio
    import base64
    from pathlib import Path

    code = state["code"].html_code
    attempt = state.get("vision_attempt", 0) + 1
    run_dir = output.run_dir()

    # Save HTML to temp file for Playwright
    html_path = run_dir / f"vision_check_attempt_{attempt}.html"
    html_path.write_text(code, encoding="utf-8")

    # Screenshot with Playwright
    screenshot_path = run_dir / f"vision_screenshot_attempt_{attempt}.png"

    async def capture():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 720, "height": 1280})
            await page.goto(html_path.as_uri(), wait_until="networkidle")
            # Wait for game to initialize and run a few frames
            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(screenshot_path), full_page=False)
            await browser.close()

    try:
        asyncio.run(capture())
        print(f"  [verify_vision] Screenshot saved -> {output.rel(screenshot_path)}")
    except Exception as e:
        print(f"  [verify_vision] Playwright error: {e}")
        # Return failed review if screenshot fails
        return {"vision_review": CodeReview(
            passed=False, score=1,
            strengths=[], issues=[f"Vision check failed: {e}"], suggestions=[]
        ), "vision_attempt": attempt, "vision_screenshot_path": str(screenshot_path)}

    # Encode screenshot for vision model
    with open(screenshot_path, "rb") as f:
        screenshot_b64 = base64.b64encode(f.read()).decode()

    # Vision model review
    llm = _make_llm(VISION_MODEL, temperature=0.3, max_tokens=_max_tokens(VISION_MODEL, 1024))
    structured_llm = llm.with_structured_output(CodeReview, method="function_calling")

    gdd = state["gdd"]
    impl_spec = state["impl_spec"]

    prompt = VISION_VERIFY_PROMPT.format(
        title=gdd.title,
        genre=state["genre"],
        core_loop="; ".join(gdd.core_loop[:3]),
        visual_elements=gdd.visual_style,
        juice_list="; ".join(gdd.juice_list[:5]),
    )

    # Multimodal call: checklist prompt + screenshot to the vision model
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
            },
        ]
    )

    try:
        review = invoke_with_retry(structured_llm, [message])
        if review is None:
            review = CodeReview(
                passed=False, score=4,
                strengths=[],
                issues=["Vision review returned no structured output"],
                suggestions=["Check VISION_MODEL supports function calling"],
            )
    except Exception as e:
        # Non-function-calling or vision-incapable model must not crash the run;
        # score as a soft fail so the rework loop runs with a real diagnosis.
        print(f"  [verify_vision] Vision review error: {e}")
        review = CodeReview(
            passed=False, score=5,
            strengths=[],
            issues=[f"Vision model review failed: {e}"],
            suggestions=["Check VISION_MODEL supports image input + function calling"],
        )

    path = output.save("05_vision", "review.json", review.model_dump(), attempt=attempt)
    print(f"  [verify_vision] Score {review.score}/10 -> {output.rel(path)}")

    return {
        "vision_review": review,
        "vision_attempt": attempt,
        "vision_screenshot_path": str(screenshot_path)
    }


def should_rework_vision(state: PipelineState) -> str:
    """Conditional edge: vision pass -> playtest, fail -> rework code."""
    review = state.get("vision_review")
    attempt = state.get("vision_attempt", 1)

    if review and review.passed and review.score >= 7:
        return "run_playtest"

    if attempt >= MAX_VISION_ATTEMPTS:
        return "run_playtest"  # Don't block on vision

    return "generate_code"


# ============================================================
# NEW NODE: Playtest Agent — Headless Browser Plays Game
# ============================================================
PLAYTEST_PROMPT = """\
You are a playtest analyst. A headless browser played the game for 30 seconds.
Here are the telemetry results:

PLAYTEST RESULTS:
{playtest_json}

Game: **{title}** | Genre: **{genre}**
Expected core loop: {core_loop}

ANALYZE:
1. **Playability** — Did the game run without crashes? (crashed: {crashed})
2. **Score achieved** — {score} (expected range for 30s: 100-10000 depending on genre)
3. **Survival time** — {survival_time}s out of 30s test
4. **Actions per second** — {aps} (indicator of engagement)
5. **Death cause** — {death_cause}
6. **FPS average** — {fps} (target: 55+)
7. **Controls responsive** — {controls_responsive}

SCORING (1-10):
- 9-10: Fun, balanced, performs well, good survival, engaging
- 7-8: Playable, minor balance/performance issues
- 5-6: Significant issues — too hard/easy, laggy, confusing
- 1-4: Broken — crashes, unplayable, 0 score, instant death

Provide specific feedback for code rework if score < 7.
"""


def run_playtest(state: PipelineState) -> PipelineState:
    """Run headless playtest using Playwright with simulated inputs."""
    from playwright.async_api import async_playwright
    import asyncio
    import json
    import random

    code = state["code"].html_code
    attempt = state.get("playtest_attempt", 0) + 1
    run_dir = output.run_dir()

    html_path = run_dir / f"playtest_attempt_{attempt}.html"
    html_path.write_text(code, encoding="utf-8")

    # Playtest telemetry collector (injected into page)
    telemetry_script = """
    window.__playtest_telemetry = {
        score: 0,
        actions: 0,
        startTime: Date.now(),
        crashes: [],
        fpsSamples: [],
        deathCause: null,
        lastFrameTime: 0,
        frameCount: 0
    };

    // Hook into Phaser game loop if possible
    const originalRequestAnimationFrame = window.requestAnimationFrame;
    window.requestAnimationFrame = function(cb) {
        return originalRequestAnimationFrame(function(timestamp) {
            window.__playtest_telemetry.frameCount++;
            if (window.__playtest_telemetry.lastFrameTime) {
                const dt = timestamp - window.__playtest_telemetry.lastFrameTime;
                if (dt > 0) window.__playtest_telemetry.fpsSamples.push(1000 / dt);
            }
            window.__playtest_telemetry.lastFrameTime = timestamp;
            cb(timestamp);
        });
    };

    // Hook console.error
    const origError = console.error;
    console.error = function(...args) {
        window.__playtest_telemetry.crashes.push(args.join(' '));
        origError.apply(console, args);
    };
    """

    async def playtest():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 720, "height": 1280})

            # Inject telemetry
            await page.add_init_script(telemetry_script)

            await page.goto(html_path.as_uri(), wait_until="networkidle")
            await page.wait_for_timeout(2000)  # Let game initialize

            # Simulate gameplay for 30 seconds
            test_duration = 30000  # ms
            start_time = asyncio.get_event_loop().time() * 1000

            async def record_action():
                await page.evaluate(
                    "() => { window.__playtest_telemetry.actions++; }"
                )

            while (asyncio.get_event_loop().time() * 1000 - start_time) < test_duration:
                # Random inputs: tap/click for jump, swipe for lane change
                action_type = random.choice(["tap", "swipe_left", "swipe_right", "hold"])

                if action_type == "tap":
                    await page.mouse.click(360, 640)
                elif action_type == "swipe_left":
                    await page.mouse.move(360, 640)
                    await page.mouse.down()
                    await page.mouse.move(100, 640, steps=5)
                    await page.mouse.up()
                elif action_type == "swipe_right":
                    await page.mouse.move(360, 640)
                    await page.mouse.down()
                    await page.mouse.move(620, 640, steps=5)
                    await page.mouse.up()
                elif action_type == "hold":
                    await page.mouse.down()
                    await asyncio.sleep(0.1)
                    await page.mouse.up()

                await record_action()
                await asyncio.sleep(random.uniform(0.1, 0.5))

            # Extract telemetry
            telemetry = await page.evaluate("() => window.__playtest_telemetry")

            # Best-effort score extraction: the codegen prompts require the game
            # to persist its score in localStorage and render it on the HUD.
            # Keys like "highScore"/"best" are excluded so a stale record is
            # never reported as the current playtest score.
            score_info = await page.evaluate(
                """() => {
                const read = v => {
                    if (v === null || v === undefined) return null;
                    const m = String(v).match(/-?\\d+/);
                    return m ? parseInt(m[0], 10) : null;
                };
                for (let i = 0; i < localStorage.length; i++) {
                    const k = localStorage.key(i);
                    if (/high|best/i.test(k)) continue;
                    if (/score/i.test(k)) {
                        const n = read(localStorage.getItem(k));
                        if (n !== null) return {score: n, source: 'localStorage:' + k};
                    }
                }
                const el = document.querySelector('#score, .score, [class*="score"], [id*="score"]');
                if (el) {
                    const n = read(el.textContent);
                    if (n !== null) return {score: n, source: 'dom'};
                }
                return {score: 0, source: 'none'};
            }"""
            )
            telemetry["score"] = score_info["score"]
            telemetry["scoreSource"] = score_info["source"]
            await browser.close()
            return telemetry

    try:
        telemetry = asyncio.run(playtest())

        # Calculate metrics
        fps_avg = sum(telemetry.get("fpsSamples", [60])) / max(len(telemetry.get("fpsSamples", [60])), 1)
        survival_time = min(30, (telemetry.get("frameCount", 0) / 60))
        crashed = len(telemetry.get("crashes", [])) > 0

        playtest_data = {
            "score": telemetry.get("score", 0),
            "score_source": telemetry.get("scoreSource", "none"),
            "actions": telemetry.get("actions", 0),
            "aps": telemetry.get("actions", 0) / 30,
            "survival_time": survival_time,
            "crashed": crashed,
            "crash_details": telemetry.get("crashes", []),
            "fps_avg": round(fps_avg, 1),
            "death_cause": telemetry.get("deathCause", "unknown"),
            "controls_responsive": not crashed and fps_avg > 30,
        }

        # Save telemetry
        telemetry_path = run_dir / f"playtest_telemetry_attempt_{attempt}.json"
        telemetry_path.write_text(json.dumps(playtest_data, indent=2), encoding="utf-8")
        print(f"  [run_playtest] Telemetry saved -> {output.rel(telemetry_path)}")

    except Exception as e:
        print(f"  [run_playtest] Error: {e}")
        playtest_data = {
            "score": 0, "actions": 0, "aps": 0, "survival_time": 0,
            "crashed": True, "crash_details": [str(e)], "fps_avg": 0,
            "death_cause": "playtest_error", "controls_responsive": False
        }

    # LLM analysis of playtest results
    llm = _make_llm(REVIEW_MODEL, temperature=0.3, max_tokens=_max_tokens(REVIEW_MODEL, 1024))
    structured_llm = llm.with_structured_output(CodeReview, method="function_calling")

    gdd = state["gdd"]
    prompt = PLAYTEST_PROMPT.format(
        title=gdd.title,
        genre=state["genre"],
        core_loop="; ".join(gdd.core_loop[:3]),
        playtest_json=json.dumps(playtest_data, indent=2),
        **playtest_data,
        fps=playtest_data["fps_avg"],
    )

    review = invoke_with_retry(structured_llm, prompt)
    if review is None:
        review = CodeReview(
            passed=False, score=4,
            strengths=[],
            issues=["Playtest review returned no structured output"],
            suggestions=["Check REVIEW_MODEL supports function calling"],
        )

    status = "passed" if review.passed and review.score >= 7 else "needs rework"
    path = output.save("06_playtest", "review.json", review.model_dump(), attempt=attempt)
    print(f"  [run_playtest] Score {review.score}/10 ({status}) -> {output.rel(path)}")

    return {
        "playtest_results": playtest_data,
        "playtest_review": review,
        "playtest_attempt": attempt,
    }


def should_rework_playtest(state: PipelineState) -> str:
    """Conditional edge: playtest pass or attempts exhausted -> END, fail -> rework code."""
    review = state.get("playtest_review")
    attempt = state.get("playtest_attempt", 1)

    if review and review.passed and review.score >= 7:
        return END

    if attempt >= MAX_PLAYTEST_ATTEMPTS:
        return END

    return "generate_code"


# ---------------------------------------------------------------------------
# Graph wiring
# ---------------------------------------------------------------------------
def build_graph(checkpointer=None):
    """Build and compile the game design pipeline graph.

    Flow:
        START -> research_genre -> generate_gdd -> review_gdd ─┬─ (fail) -> generate_gdd
                                                             └─ (pass) -> human_review_gdd
                                                                           │
                            ┌── (reject) ──────────────────────────────────┘
                            ↓                                  │
                       generate_gdd ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─    │
                                                               └─ (approve)
                                                                     ↓
        generate_impl_spec -> review_impl_spec ─┬─ (fail) -> human_review_impl_spec
                                               └─ (pass) -> generate_code
                                                                  │
                            ┌── (fix) ───────────────────────────┤
                            ↓                                      └─ (approve)
                       generate_impl_spec ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
                                                               ↓
        generate_code -> review_code ─┬─ (fail) -> generate_code
                                      └─ (pass) -> verify_vision
                                                         │
                                          ┌─────────────┼──────────────┐
                                          ↓             ↓              ↓
                                   (fail, attempts  (max attempts)   (pass)
                                    left)               ↓              ↓
                                          ↓         run_playtest  run_playtest
                                     generate_code
                                                                       │
                                                ┌──────────────────────┴───┐
                                                ↓                          ↓
                                          (fail, attempts left)      (pass/max) -> END
                                                ↓
                                          generate_code
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
    builder.add_node("generate_code", generate_code)
    builder.add_node("review_code", review_code)
    builder.add_node("verify_vision", verify_vision)
    builder.add_node("run_playtest", run_playtest)

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

    # Edges — Code gen cycle
    builder.add_edge("generate_code", "review_code")
    builder.add_conditional_edges("review_code", should_rework_code)

    # Edges — Vision verification: conditional only (fixed + conditional edges
    # on the same node are ambiguous in LangGraph; should_rework_vision owns all
    # routing: pass -> run_playtest, fail/max attempts -> generate_code/run_playtest).
    builder.add_conditional_edges("verify_vision", should_rework_vision)

    # Edges — Playtest: pass or attempts exhausted -> END, fail -> generate_code.
    builder.add_conditional_edges("run_playtest", should_rework_playtest)

    return builder.compile(checkpointer=checkpointer)
