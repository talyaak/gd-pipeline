"""Structured output schemas for the game pipeline."""

from pydantic import BaseModel, Field


class GenreAnalysis(BaseModel):
    """Structured analysis of a game genre for hyper-casual HTML5 games."""

    genre: str = Field(description="The genre that was analyzed")

    core_mechanics: list[str] = Field(
        description=(
            "The 3-5 essential mechanics that define this genre. "
            "Focus on what the player actually DOES moment-to-moment."
        )
    )

    game_feel_juice: list[str] = Field(
        description=(
            "Specific juice/game-feel techniques that top games in this genre use. "
            "Screen shake, particle effects, easing curves, sound design cues, etc."
        )
    )

    progression_patterns: list[str] = Field(
        description=(
            "How games in this genre keep players engaged over time. "
            "Difficulty curves, unlock systems, score chasing, meta-loops."
        )
    )

    common_mistakes: list[str] = Field(
        description=(
            "What indie/hyper-casual devs get wrong in this genre. "
            "Things that kill retention or feel bad."
        )
    )

    retention_hooks: list[str] = Field(
        description=(
            "What makes top games in this genre sticky. "
            "The specific reasons players come back for another session."
        )
    )

    reference_games: list[str] = Field(
        description=(
            "3-5 reference games (preferably browser/mobile) that nail this genre. "
            "Include what each one does particularly well."
        )
    )


class GddReview(BaseModel):
    """Result of reviewing a Game Design Document for quality and completeness."""

    passed: bool = Field(
        description=(
            "True if the GDD is good enough to move to implementation. "
            "False if it needs rework."
        )
    )

    score: int = Field(
        description=(
            "Quality score from 1-10. "
            "7+ means pass. Below 7 means rework is needed."
        )
    )

    strengths: list[str] = Field(
        description="What the GDD does well — keep these in the next iteration."
    )

    issues: list[str] = Field(
        description=(
            "Specific problems that must be fixed. Each issue should be actionable, "
            'e.g. "Core loop is too vague — describe exact player inputs per second" '
            'not "needs more detail".'
        )
    )

    suggestions: list[str] = Field(
        description=(
            "Optional improvements that would make the GDD stronger but aren't blockers."
        )
    )


class GameDesignDocument(BaseModel):
    """Concrete game design document for a hyper-casual HTML5 browser game."""

    title: str = Field(
        description="Working title for the game — catchy, memorable, marketable."
    )

    one_liner: str = Field(
        description=(
            "Single-sentence elevator pitch. "
            'e.g. "Vampire Survivors meets Breakout in a 2-minute browser session."'
        )
    )

    core_loop: list[str] = Field(
        description=(
            "Step-by-step description of the moment-to-moment gameplay loop. "
            "What does the player do every 5-10 seconds?"
        )
    )

    controls: str = Field(
        description=(
            "Exact control scheme. Primary input (mouse/touch/keyboard), "
            "what each input does. Keep it to 1-2 inputs max for hyper-casual."
        )
    )

    visual_style: str = Field(
        description=(
            "Art direction in 2-3 sentences. Specific references, color palette mood, "
            "perspective (top-down, side-view, isometric). "
            "Must be achievable by a solo dev or with free assets."
        )
    )

    mechanics: list[str] = Field(
        description=(
            "Detailed list of 4-6 game mechanics. Each entry should describe "
            "WHAT it is, HOW it works, and WHY it's fun."
        )
    )

    progression_system: str = Field(
        description=(
            "How the game keeps players engaged across sessions. "
            "Unlocks, difficulty scaling, meta-progression, leaderboards, etc. "
            "Be specific about pacing and numbers."
        )
    )

    juice_list: list[str] = Field(
        description=(
            "5-8 specific game-feel / juice items to implement. "
            "Each should be a concrete technique with parameters, "
            'e.g. "0.05s hit-freeze on enemy kill + 12-particle radial burst".'
        )
    )

    mvp_scope: list[str] = Field(
        description=(
            "Ordered list of features for a playable MVP (build this first). "
            "Should be achievable in 1-2 weeks. Cut ruthlessly."
        )
    )

    post_mvp: list[str] = Field(
        description=(
            "Features to add after MVP is validated. "
            "Polish, meta-game, monetization hooks, additional content."
        )
    )


class ImplSpecReview(BaseModel):
    """Result of reviewing an Implementation Spec for completeness and buildability."""

    passed: bool = Field(
        description=(
            "True if the spec is detailed enough to start coding. "
            "False if it needs rework."
        )
    )

    score: int = Field(
        description=(
            "Quality score from 1-10. "
            "7+ means pass. Below 7 means rework is needed."
        )
    )

    strengths: list[str] = Field(
        description="What the spec does well — keep these in the next iteration."
    )

    issues: list[str] = Field(
        description=(
            "Specific problems that must be fixed. Each issue should be actionable, "
            'e.g. "Enemy entity has no spawn_rate property — needed for the wave system" '
            'not "missing details".'
        )
    )

    suggestions: list[str] = Field(
        description=(
            "Optional improvements that would strengthen the spec but aren't blockers."
        )
    )


# ---------------------------------------------------------------------------
# Step 3: Implementation Spec
# ---------------------------------------------------------------------------

class PropertyDef(BaseModel):
    """A single property on a game entity."""

    name: str = Field(description="Property name, e.g. 'speed', 'hp'.")
    type_description: str = Field(
        description=(
            "Type + description, e.g. 'number — pixels/sec, default 300'."
        )
    )


class EntityDef(BaseModel):
    """Definition of a game entity / object."""

    name: str = Field(description="Entity name in PascalCase, e.g. 'PlayerShip'.")
    properties: list[PropertyDef] = Field(
        description=(
            "All properties for this entity. "
            "Include type, default value, and brief description for each."
        )
    )
    behavior: str = Field(
        description=(
            "1-3 sentence description of what this entity does each frame "
            "and how it interacts with other entities."
        )
    )


class GameState(BaseModel):
    """A state in the game's top-level state machine."""

    name: str = Field(description="State name, e.g. 'Playing', 'GameOver', 'Paused'.")
    description: str = Field(description="What happens in this state.")
    transitions: list[str] = Field(
        description=(
            "List of transitions OUT of this state. "
            'Format: "event → TargetState", e.g. "player_dies → GameOver".'
        )
    )


class BalanceParam(BaseModel):
    """A single tunable game parameter."""

    name: str = Field(description="Parameter name, e.g. 'player_speed'.")
    value: str = Field(
        description=(
            "Value + unit + rationale, "
            "e.g. '300 px/s — fast enough to dodge, slow enough to require planning'."
        )
    )


class BalanceTable(BaseModel):
    """A set of tunable game parameters with concrete starting values."""

    category: str = Field(
        description="Category name, e.g. 'Player', 'Enemies', 'Scoring', 'Difficulty'."
    )
    params: list[BalanceParam] = Field(
        description=(
            "All tunable parameters in this category. "
            "Every number in the game should appear here with a starting value "
            "and brief rationale."
        )
    )


class AssetEntry(BaseModel):
    """A single asset needed for the game."""

    name: str = Field(description="Asset identifier, e.g. 'spr_player', 'sfx_explosion'.")
    asset_type: str = Field(
        description="One of: sprite, spritesheet, sound, music, font, particle."
    )
    description: str = Field(
        description="What this asset looks like / sounds like. Enough detail to create or source it."
    )


class ImplementationSpec(BaseModel):
    """Technical implementation spec — bridge between GDD and code."""

    entities: list[EntityDef] = Field(
        description=(
            "All game entities/objects with their properties and behaviors. "
            "Include player, enemies, projectiles, pickups, UI elements — "
            "everything that exists in the game world."
        )
    )

    state_machine: list[GameState] = Field(
        description=(
            "Top-level game state machine. Must include at least: "
            "Loading, Playing, GameOver. Add states as needed (Paused, LevelUp, etc.)."
        )
    )

    balance_tables: list[BalanceTable] = Field(
        description=(
            "Concrete balance/tuning parameters grouped by category. "
            "Every number in the game should be here with a starting value "
            "and brief rationale. Think: what would you put in a config.json?"
        )
    )

    scene_flow: list[str] = Field(
        description=(
            "Ordered list of screens/scenes the player moves through. "
            'Format: "SceneName — description", '
            'e.g. "TitleScreen — logo + tap to start, no menus".'
        )
    )

    asset_manifest: list[AssetEntry] = Field(
        description=(
            "Complete list of visual and audio assets needed for the MVP. "
            "Be specific about dimensions, frame counts, and style."
        )
    )

    technical_notes: list[str] = Field(
        description=(
            "Implementation-specific notes: collision approach, rendering strategy, "
            "performance considerations, recommended libraries/frameworks, "
            "canvas vs WebGL, etc."
        )
    )

    example_chunks: list[dict] = Field(
        default_factory=list,
        description=(
            "3–5 concrete JSON chunk examples for games with chunk/pattern spawning. "
            "Each dict represents one chunk (id, duration, spawns, etc.). "
            "Required for endless runners, lane games, procedural levels. "
            "Empty list if game has no chunk system."
        ),
    )


# ---------------------------------------------------------------------------
# Step 4: Code Generation
# ---------------------------------------------------------------------------

class GeneratedGame(BaseModel):
    """A complete single-file HTML5 browser game."""

    html_code: str = Field(
        description=(
            "Complete, runnable HTML5 document with embedded CSS and JavaScript. "
            "Must open in a browser and be immediately playable — no build step, "
            "no external dependencies, no module imports."
        )
    )

    implementation_notes: list[str] = Field(
        description=(
            "Brief notes about implementation decisions, any deviations from "
            "the spec, and known limitations."
        )
    )


# ---------------------------------------------------------------------------
# Step 5: Code Review
# ---------------------------------------------------------------------------

class CodeReview(BaseModel):
    """Review of generated game code against the implementation spec."""

    passed: bool = Field(
        description=(
            "True if the code is playable and reasonably matches the spec. "
            "False if there are blocking bugs or major missing features."
        )
    )

    score: int = Field(
        description=(
            "Quality score from 1-10. "
            "7+ means pass. Below 7 means rework is needed."
        )
    )

    strengths: list[str] = Field(
        description="What the code does well — keep these in rework iterations."
    )

    issues: list[str] = Field(
        description=(
            "Specific bugs, missing features, or spec deviations that must be fixed. "
            "Reference function names, expected vs actual behavior."
        )
    )

    suggestions: list[str] = Field(
        description="Optional improvements that aren't blockers."
    )
