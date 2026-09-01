from typing import Literal, Optional, TypedDict

from pydantic import BaseModel, Field


class GenreAnalysis(BaseModel):
    core_mechanics: list[str] = Field(description="The 2-4 mechanics that define this genre")
    juice: list[str] = Field(description="Feedback/juice techniques typical of this genre (screen shake, particles, sound cues, etc.)")
    progression: str = Field(description="How difficulty/reward scales over a play session")
    common_mistakes: list[str] = Field(description="Pitfalls that make implementations of this genre feel bad")
    reference_games: list[str] = Field(description="1-3 well-known games in this genre")


class GameDesignDocument(BaseModel):
    title: str
    core_loop: str = Field(description="One paragraph describing the second-to-second gameplay loop")
    controls: str = Field(description="Exact input scheme, e.g. 'Spacebar to jump, hold to jump higher'")
    mechanics: list[str]
    juice: list[str]
    mvp_scope: str = Field(description="What is explicitly IN scope for a single-file MVP build")
    win_lose_condition: str


class EntitySpec(BaseModel):
    name: str
    properties: list[str]
    behavior: str


class ImplementationSpec(BaseModel):
    entities: list[EntitySpec]
    state_machine: list[str] = Field(description="Ordered list of game states, e.g. ['Boot', 'Play', 'GameOver']")
    mraid_state_machine: list[str] = Field(
        default_factory=lambda: ["loading", "ready", "visible", "playing", "paused", "gameover"],
        description="MRAID lifecycle states in order: loading -> ready -> visible -> playing -> paused/gameover. Must match MRAID spec."
    )
    balance: dict[str, str] = Field(description="Key tunable values as strings, e.g. {'gravity': '800', 'jump_velocity': '-400'}")
    example_chunks: list[str] = Field(
        default_factory=list,
        description="Concrete worked examples (as short code/pseudocode snippets) for any procedural/generative subsystem, e.g. obstacle spawning patterns. Required if the genre has procedural content.",
    )
    technical_notes: list[str] = Field(
        description="Constraints for the coder: must use Phaser 3, procedural textures via graphics.generateTexture(), Web Audio API only, no external asset files, delta time variable must be named 'dt'"
    )
    target_session_seconds: int = Field(
        default=30,
        description="Target total session length in seconds (tutorial + core loop). Typical range: 15-40s for playable ads."
    )
    tutorial_duration_seconds: int = Field(
        default=5,
        description="Target tutorial/onboarding duration in seconds. Should be substantive but brief. Typical range: 3-8s."
    )
    time_to_first_interaction_target_seconds: int = Field(
        default=4,
        description="Target time-to-first-interaction in seconds. Must be under 4s for good retention per industry benchmarks."
    )


class CodeReview(BaseModel):
    score: int = Field(ge=1, le=10, description="Overall score, 1-10. Runtime correctness issues auto-cap this at 3.")
    spec_fidelity_issues: list[str] = Field(default_factory=list, description="Ways the code deviates from the GDD/spec")
    quality_issues: list[str] = Field(default_factory=list, description="Code quality/juice concerns, given execution evidence already proved runtime correctness")
    strengths: list[str] = Field(default_factory=list)


class ExecutionReport(BaseModel):
    """Objective evidence from actually running the generated game in a browser. Populated starting Milestone 3."""

    loaded: bool
    console_errors: list[str] = Field(default_factory=list)
    canvas_rendered: bool = False
    input_response_detected: bool = False
    screenshot_before_path: Optional[str] = None
    screenshot_after_path: Optional[str] = None
    duration_ms: Optional[int] = None
    time_to_first_interaction_ms: Optional[int] = Field(
        default=None,
        description="Measured time from page load to first meaningful user interaction (pointerdown/keyup). None if not measured."
    )
    engagement_duration_ms: Optional[int] = Field(
        default=None,
        description="Measured time the game remained in an active playable state (e.g., PLAYING state) before completing or stopping. None if not measured."
    )
    completion_rate: Optional[float] = Field(
        default=None,
        description="Fraction of target session completed (0.0 to 1.0). For example, 0.75 means 75% of the target session was completed. None if not measured."
    )
    final_html: Optional[str] = Field(
        default=None,
        description="The exact HTML that was served and tested (post Phaser/MRAID injection). This is the only artifact that should ever be shipped as game.html."
    )


class StageResult(TypedDict, total=False):
    status: Literal["pending", "passed", "failed_needs_rework", "failed_max_attempts", "skipped"]
    attempt: int
    artifact: Optional[dict]
    review: Optional[dict]
    error: Optional[str]


class RunState(TypedDict, total=False):
    run_id: str
    run_dir: str
    brief: str
    research: StageResult
    design: StageResult
    spec: StageResult
    code: StageResult
    execution: StageResult
    variants: StageResult
    human_feedback: Optional[str]