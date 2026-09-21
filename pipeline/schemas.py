"""Structured output schemas for the game pipeline."""

from pydantic import BaseModel, Field
from typing import Optional, Literal


# ============================================================
# GAMIFICATION SCIENCE SCHEMAS (Octalysis, Hook Model, SDT)
# ============================================================

class OctalysisDriver(BaseModel):
    """One of the 8 Octalysis core drives."""
    driver: Literal[
        "Epic Meaning & Calling",
        "Development & Accomplishment",
        "Empowerment of Creativity & Feedback",
        "Ownership & Possession",
        "Social Influence & Relatedness",
        "Scarcity & Impatience",
        "Unpredictability & Curiosity",
        "Loss & Avoidance"
    ]
    weight: int = Field(ge=1, le=10, description="How central this drive is (1-10)")
    implementation: str = Field(description="Specific mechanic implementing this drive")


class HookModelLoop(BaseModel):
    """Nir Eyal's Hook Model: Trigger -> Action -> Reward -> Investment"""
    trigger_type: Literal["external", "internal"]
    trigger_description: str
    action: str = Field(description="Simplest behavior in anticipation of reward")
    reward_type: Literal["tribe", "hunt", "self"]
    reward_description: str
    investment: str = Field(description="User puts something in to increase next trigger likelihood")


class PlayerArchetype(BaseModel):
    """Bartle/Richard Bartle types + modern extensions"""
    archetype: Literal["Achiever", "Explorer", "Socializer", "Killer", "Customizer", "Competitor"]
    percentage: int = Field(ge=0, le=100, description="Target audience %")
    key_motivators: list[str]
    retention_mechanics: list[str]


class MotivationProfile(BaseModel):
    """Self-Determination Theory: Autonomy, Competence, Relatedness"""
    autonomy_features: list[str] = Field(description="Choices, customization, self-expression")
    competence_features: list[str] = Field(description="Clear goals, feedback, optimal challenge")
    relatedness_features: list[str] = Field(description="Social features, shared experiences")


class DynamicDifficultyConfig(BaseModel):
    """Dynamic Difficulty Adjustment (DDA) specification"""
    enabled: bool = True
    target_failure_rate: float = Field(default=0.3, ge=0.1, le=0.5, description="Target % of failed attempts")
    measurement_window_sec: int = Field(default=60, description="Window to measure performance")
    adjustment_factors: dict[str, float] = Field(
        default_factory=lambda: {"spawn_rate": 0.1, "enemy_speed": 0.05, "player_power": 0.08},
        description="How much each parameter can adjust per window"
    )
    min_max_bounds: dict[str, list[float]] = Field(
        description="Min/max for each tunable: {'spawn_rate': [0.5, 2.0]}"
    )
    cooldown_sec: int = Field(default=30, description="Minimum time between adjustments")


class DailyRewardSystem(BaseModel):
    """Daily login / streak reward system"""
    enabled: bool = True
    streak_rewards: list[dict] = Field(description="Day N: {reward_type, amount, description}")
    streak_break_penalty: str = Field(description="What happens when streak breaks")
    comeback_bonus: Optional[str] = Field(default=None, description="Bonus for returning after absence")


class BattlePassSpec(BaseModel):
    """Battle pass / season pass specification"""
    enabled: bool = False
    duration_days: int = Field(default=30)
    free_track: list[dict] = Field(description="Free tier rewards per level")
    premium_track: list[dict] = Field(description="Premium tier rewards per level")
    xp_sources: list[str] = Field(description="Activities that grant battle pass XP")


class SocialSpec(BaseModel):
    """Social features specification"""
    leaderboards: bool = True
    leaderboard_types: list[str] = Field(default_factory=lambda: ["global", "friends", "daily"])
    share_mechanics: list[str] = Field(default_factory=lambda: ["score_screenshot", "replay_clip"])
    guilds_clans: bool = False
    co_op_modes: list[str] = Field(default_factory=list)
    pvp_modes: list[str] = Field(default_factory=list)


class AdaptiveAudioSpec(BaseModel):
    """Adaptive / procedural audio specification"""
    layers: list[dict] = Field(description="Audio layers: {name, trigger_condition, intensity_range}")
    spatial_audio: bool = False
    procedural_music: bool = True
    dynamic_mixing: bool = True
    haptic_sync: bool = False


class HapticSpec(BaseModel):
    """Haptic feedback specification (Gamepad Vibration API, iOS/Android)"""
    enabled: bool = True
    events: list[dict] = Field(description="Events: {event_name, pattern, intensity, duration_ms}")
    gamepad_support: bool = True
    mobile_vibration: bool = True


class VisualPolishSpec(BaseModel):
    """Advanced visual polish: shaders, post-processing, effects"""
    post_processing: list[str] = Field(default_factory=lambda: ["bloom", "color_grading", "vignette"])
    shaders: list[dict] = Field(default_factory=list, description="Custom shaders: {name, type, params}")
    particle_systems: list[dict] = Field(default_factory=list)
    screen_effects: list[str] = Field(default_factory=lambda: ["chromatic_aberration", "screen_shake", "hit_freeze", "flash"])
    webgpu_target: bool = False


class TelemetryEvent(BaseModel):
    """Single telemetry event definition"""
    event_name: str
    properties: dict[str, str] = Field(description="Property name -> type (string, number, bool)")
    trigger: str = Field(description="When this fires")


class ABTestConfig(BaseModel):
    """A/B test configuration for balance values"""
    enabled: bool = False
    variants: dict[str, dict] = Field(description="Variant name -> parameter overrides")
    allocation: dict[str, float] = Field(description="Variant -> traffic %")
    success_metric: str = Field(description="Metric to optimize: retention_d1, session_time, etc.")


class LiveOpsConfig(BaseModel):
    """Live operations / remote config specification"""
    enabled: bool = False
    remote_config_keys: list[str] = Field(description="Keys that can be updated remotely")
    content_update_schedule: str = Field(description="e.g., 'weekly', 'biweekly'")
    feature_flags: list[str] = Field(default_factory=list)


class GamificationSpec(BaseModel):
    """Complete gamification specification bundle"""
    octalysis_drivers: list[OctalysisDriver] = Field(default_factory=list, min_length=1, max_length=8)
    hook_loops: list[HookModelLoop] = Field(default_factory=list, min_length=1)
    player_archetypes: list[PlayerArchetype] = Field(default_factory=list)
    motivation_profile: Optional[MotivationProfile] = None
    dda_config: Optional[DynamicDifficultyConfig] = None
    daily_rewards: Optional[DailyRewardSystem] = None
    battle_pass: Optional[BattlePassSpec] = None
    social: Optional[SocialSpec] = None
    adaptive_audio: Optional[AdaptiveAudioSpec] = None
    haptic: Optional[HapticSpec] = None
    visual_polish: Optional[VisualPolishSpec] = None
    telemetry_events: list[TelemetryEvent] = Field(default_factory=list)
    ab_test: Optional[ABTestConfig] = None
    live_ops: Optional[LiveOpsConfig] = None


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

    gamification: Optional[GamificationSpec] = Field(
        default=None,
        description="Complete gamification science specification (Octalysis, Hook Model, SDT, DDA, retention systems)"
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

    gamification_impl: Optional[GamificationSpec] = Field(
        default=None,
        description="Implementation-ready gamification spec with concrete telemetry events, A/B config, live ops"
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
