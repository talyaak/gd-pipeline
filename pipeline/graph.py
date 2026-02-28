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

LLM_MODEL = "gpt-5.2"

MAX_GDD_ATTEMPTS = 3
MAX_IMPL_SPEC_ATTEMPTS = 3
MAX_CODE_ATTEMPTS = 3


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
    """Call GPT-4o with structured output to produce a GenreAnalysis."""
    llm = ChatOpenAI(
        model=LLM_MODEL,
        temperature=0.3,
        max_tokens=4096,
    )

    # .with_structured_output() makes the LLM return a Pydantic model directly
    structured_llm = llm.with_structured_output(GenreAnalysis)

    analysis = structured_llm.invoke(
        RESEARCH_PROMPT.format(genre=state["genre"])
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
        max_tokens=4096,
    )

    structured_llm = llm.with_structured_output(GameDesignDocument)

    analysis_json = state["analysis"].model_dump_json(indent=2)
    attempt = state.get("gdd_attempt", 0) + 1
    review = state.get("gdd_review")
    human_feedback = state.get("human_feedback")

    if (review and not review.passed) or human_feedback:
        # Rework: feed previous GDD + feedback into a focused rework prompt
        previous_gdd_json = state["gdd"].model_dump_json(indent=2)
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

    gdd = structured_llm.invoke(prompt)

    path = output.save("02_gdd", "gdd.json", gdd.model_dump(), attempt=attempt)
    print(f"  [generate_gdd] Attempt {attempt} → {output.rel(path)}")

    return {"gdd": gdd, "gdd_attempt": attempt, "human_feedback": None}


# ---------------------------------------------------------------------------
# Node: review_gdd
# ---------------------------------------------------------------------------
REVIEW_GDD_PROMPT = """\
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
        model=LLM_MODEL,
        temperature=0.3,
        max_tokens=4096,
    )

    structured_llm = llm.with_structured_output(GddReview)

    gdd_json = state["gdd"].model_dump_json(indent=2)

    review = structured_llm.invoke(
        REVIEW_GDD_PROMPT.format(genre=state["genre"], gdd_json=gdd_json)
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

Be ruthlessly practical. A developer should be able to `npm init` and start \
building from this spec.
"""


REWORK_IMPL_SPEC_PROMPT = """\
You are a senior game programmer REVISING a technical implementation spec based \
on reviewer feedback. Keep what works, fix what doesn't.

Game: **{title}**
Genre: **{genre}**

Game Design Document:
{gdd_json}

Previous implementation spec that needs improvement:
{previous_spec_json}

Reviewer feedback (score {score}/10):
Strengths (KEEP these): {strengths}
Issues (MUST FIX): {issues}
Suggestions (nice to have): {suggestions}

Generate an improved spec that addresses every issue. Do not lose the strengths. \
Every entity property needs a type and default value. Every balance number needs \
a rationale. Every asset needs dimensions.
"""


def generate_impl_spec(state: PipelineState) -> PipelineState:
    """Turn the GDD into a technical implementation spec.

    On rework attempts, incorporates review feedback to improve the spec.
    """
    llm = ChatOpenAI(
        model=LLM_MODEL,
        temperature=0.3,
        max_tokens=8192,
    )

    structured_llm = llm.with_structured_output(ImplementationSpec)

    gdd_json = state["gdd"].model_dump_json(indent=2)
    attempt = state.get("impl_spec_attempt", 0) + 1
    review = state.get("impl_spec_review")

    if review and not review.passed:
        # Rework: feed previous spec + feedback
        previous_spec_json = state["impl_spec"].model_dump_json(indent=2)
        prompt = REWORK_IMPL_SPEC_PROMPT.format(
            title=state["gdd"].title,
            genre=state["genre"],
            gdd_json=gdd_json,
            previous_spec_json=previous_spec_json,
            score=review.score,
            strengths="; ".join(review.strengths),
            issues="; ".join(review.issues),
            suggestions="; ".join(review.suggestions),
        )
    else:
        prompt = IMPL_SPEC_PROMPT.format(
            title=state["gdd"].title,
            genre=state["genre"],
            gdd_json=gdd_json,
        )

    impl_spec = structured_llm.invoke(prompt)

    path = output.save(
        "03_impl_spec", "impl_spec.json", impl_spec.model_dump(), attempt=attempt
    )
    print(f"  [generate_impl_spec] Attempt {attempt} → {output.rel(path)}")

    return {"impl_spec": impl_spec, "impl_spec_attempt": attempt}


# ---------------------------------------------------------------------------
# Node: review_impl_spec
# ---------------------------------------------------------------------------
REVIEW_IMPL_SPEC_PROMPT = """\
You are a senior technical reviewer evaluating an implementation spec for an \
HTML5 browser game. A developer will code directly from this spec — it must be \
complete and unambiguous.

Game: **{title}**
Genre: **{genre}**

Implementation Spec:
{spec_json}

Score the spec from 1-10 based on these criteria:
- **Entity completeness** (weight: 3x): Does every entity have all needed properties \
with types and default values? Are behaviors concrete, not hand-wavy?
- **Balance table coverage** (weight: 2x): Is every tunable number in the game \
present with a starting value and rationale? Could you create a config.json from this?
- **State machine clarity** (weight: 2x): Are all states and transitions covered? \
No missing edges, no dead ends?
- **Asset specificity** (weight: 1x): Are assets described well enough to create \
or source them? Dimensions, frame counts, style notes?
- **Buildability** (weight: 2x): Could a mid-level developer start coding from \
this spec today without asking clarifying questions?

Scoring guide:
- 9-10: Ready to code. Exceptional spec.
- 7-8: Good enough. Minor gaps a dev can fill.
- 5-6: Needs work. Too many missing details or inconsistencies.
- 1-4: Start over. Fundamental gaps.

Pass threshold: 7 or above.

Be specific. "Enemy entity is missing a damage property with type and default \
value — needed for the combat system described in the GDD" is useful. \
"Needs more detail" is not.
"""


def review_impl_spec(state: PipelineState) -> PipelineState:
    """Review the implementation spec for completeness and buildability."""
    llm = ChatOpenAI(
        model=LLM_MODEL,
        temperature=0.3,
        max_tokens=4096,
    )

    structured_llm = llm.with_structured_output(ImplSpecReview)

    spec_json = state["impl_spec"].model_dump_json(indent=2)

    review = structured_llm.invoke(
        REVIEW_IMPL_SPEC_PROMPT.format(
            title=state["gdd"].title,
            genre=state["genre"],
            spec_json=spec_json,
        )
    )

    attempt = state.get("impl_spec_attempt", 1)
    status = "passed" if review.passed and review.score >= 7 else "needs rework"
    path = output.save(
        "03_impl_spec", "review.json", review.model_dump(), attempt=attempt
    )
    print(f"  [review_impl_spec] Score {review.score}/10 ({status}) → {output.rel(path)}")

    return {"impl_spec_review": review}


def should_rework_impl_spec(state: PipelineState) -> str:
    """Conditional edge: decide whether to rework the impl spec or proceed to code gen."""
    review = state["impl_spec_review"]
    attempt = state.get("impl_spec_attempt", 1)

    if review.passed and review.score >= 7:
        return "generate_code"

    if attempt >= MAX_IMPL_SPEC_ATTEMPTS:
        # Avoid infinite loops — proceed with best effort
        return "generate_code"

    return "generate_impl_spec"


# ---------------------------------------------------------------------------
# Node: generate_code
# ---------------------------------------------------------------------------
CODE_GEN_PROMPT = """\
Generate a complete, single-file HTML5 Phaser 3 browser game.

Game: **{title}** | Genre: **{genre}**

GDD:
{gdd_json}

Implementation Spec:
{spec_json}

Constraints:
- ONE .html file. Only allowed external import: Phaser 3 via CDN.
- ALL graphics MUST be procedural (this.add.graphics() + generateTexture()).
  NEVER load external files. NO this.load.image(). NO this.load.audio().
  NO references to .png/.jpg/.mp3/.wav files. They do not exist.
  Use Web Audio API (new AudioContext()) for sound effects if needed.
- Implement ALL entities, states, balance values, and scenes from the spec.

Mandatory structure:

    <script src="https://cdn.jsdelivr.net/npm/phaser@3/dist/phaser.min.js"></script>
    <script>
    const CONFIG = {{ /* all balance values here */ }};

    class BootScene extends Phaser.Scene {{
        constructor() {{ super('Boot'); }}
        create() {{
            // Generate ALL textures here with graphics + generateTexture()
            const gfx = this.add.graphics();
            gfx.fillStyle(0xff0000); gfx.fillCircle(16, 16, 16);
            gfx.generateTexture('player', 32, 32); gfx.destroy();
            this.scene.start('Play');
        }}
    }}

    class PlayScene extends Phaser.Scene {{
        constructor() {{ super('Play'); }}
        create() {{ /* spawn entities using generated textures */ }}
        update(time, delta) {{
            const dt = delta / 1000;
            // Use dt everywhere
        }}
    }}

    new Phaser.Game({{
        width: 800, height: 600, scene: [BootScene, PlayScene, ...],
        physics: {{ default: 'arcade' }}
    }});
    </script>

STRICT rules (automated validation will reject violations):
- Delta time: dt = delta / 1000. NEVER use 'deltaTime' or 'elapsed'.
- ZERO external files. Every sprite = generateTexture(). Every sound = Web Audio.
- Every scene = class extending Phaser.Scene. Use Phaser arcade physics.
- Config constants at top. Game auto-sizes or fills viewport.
"""


REWORK_CODE_PROMPT = """\
Fix this Phaser 3 game based on review feedback. Output a COMPLETE .html file.

Game: **{title}** | Genre: **{genre}**

Spec: {spec_json}

Previous code:
```html
{previous_code}
```

Score {score}/10 — Strengths: {strengths}
MUST FIX: {issues}
Nice to have: {suggestions}

Same rules: Phaser 3, dt (never deltaTime), ZERO external files (generateTexture \
only), every scene extends Phaser.Scene, complete file.
"""


def generate_code(state: PipelineState) -> PipelineState:
    """Generate a complete single-file HTML5 game from the GDD + impl spec.

    On rework attempts, incorporates code review feedback.
    """
    llm = ChatOpenAI(
        model=LLM_MODEL,
        temperature=0.3,
        max_tokens=16384,
    )

    structured_llm = llm.with_structured_output(GeneratedGame)

    gdd_json = state["gdd"].model_dump_json(indent=2)
    spec_json = state["impl_spec"].model_dump_json(indent=2)
    attempt = state.get("code_attempt", 0) + 1
    review = state.get("code_review")

    if review and not review.passed:
        previous_code = state["code"].html_code
        prompt = REWORK_CODE_PROMPT.format(
            title=state["gdd"].title,
            genre=state["genre"],
            spec_json=spec_json,
            previous_code=previous_code,
            score=review.score,
            strengths="; ".join(review.strengths),
            issues="; ".join(review.issues),
            suggestions="; ".join(review.suggestions),
        )
    else:
        prompt = CODE_GEN_PROMPT.format(
            title=state["gdd"].title,
            genre=state["genre"],
            gdd_json=gdd_json,
            spec_json=spec_json,
        )

    game = structured_llm.invoke(prompt)

    # Save the playable HTML file + notes
    html_path = output.save_text(
        "04_code", "game.html", game.html_code, attempt=attempt
    )
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
Review this Phaser 3 game against its spec. Code passed automated validation \
(no external files, correct structure, variable naming), so focus on logic.

Game: **{title}** | Genre: **{genre}**

Spec: {spec_json}

Code:
```html
{code}
```

Score 1-10 (pass ≥ 7):
- **Runtime correctness** (4x): Any error that prevents gameplay = auto-fail (≤ 4).
- **Spec fidelity** (3x): All entities, states, balance values implemented?
- **Playability** (2x): Core loop works? Fun?
- **Completeness** (1x): All scenes and transitions?

Be specific: name the scene, the function, the bug, the expected behavior.
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
        model=LLM_MODEL,
        temperature=0.3,
        max_tokens=4096,
    )

    structured_llm = llm.with_structured_output(CodeReview)

    spec_json = state["impl_spec"].model_dump_json(indent=2)

    review = structured_llm.invoke(
        CODE_REVIEW_PROMPT.format(
            title=state["gdd"].title,
            genre=state["genre"],
            spec_json=spec_json,
            code=code,
        )
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
        generate_impl_spec → review_impl_spec ─┬─ (fail) → generate_impl_spec
                                               └─ (pass) → generate_code
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

    # Nodes — Code gen cycle
    builder.add_node("generate_code", generate_code)
    builder.add_node("review_code", review_code)

    # Edges — Code gen cycle
    builder.add_edge("generate_code", "review_code")
    builder.add_conditional_edges("review_code", should_rework_code)

    return builder.compile(checkpointer=checkpointer)
