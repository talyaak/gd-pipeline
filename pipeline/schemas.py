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
    balance: dict[str, str] = Field(description="Key tunable values as strings, e.g. {'gravity': '800', 'jump_velocity': '-400'}")
    example_chunks: list[str] = Field(
        default_factory=list,
        description="Concrete worked examples (as short code/pseudocode snippets) for any procedural/generative subsystem, e.g. obstacle spawning patterns. Required if the genre has procedural content.",
    )
    technical_notes: list[str] = Field(
        description="Constraints for the coder: must use Phaser 3, procedural textures via graphics.generateTexture(), Web Audio API only, no external asset files, delta time variable must be named 'dt'"
    )


class ExecutionReport(BaseModel):
    """Objective evidence from actually running the generated game in a browser. Populated starting Milestone 3."""

    loaded: bool
    console_errors: list[str] = Field(default_factory=list)
    canvas_rendered: bool = False
    input_response_detected: bool = False
    screenshot_before_path: Optional[str] = None
    screenshot_after_path: Optional[str] = None
    duration_ms: Optional[int] = None


class StageResult(TypedDict, total=False):
    status: Literal["pending", "passed", "failed_needs_rework", "failed_max_attempts", "skipped"]
    attempt: int
    artifact: Optional[dict]
    review: Optional[dict]
    error: Optional[str]


class RunState(TypedDict, total=False):
    run_id: str
    brief: str
    research: StageResult
    design: StageResult
    spec: StageResult
    code: StageResult
    execution: StageResult
    human_feedback: Optional[str]
