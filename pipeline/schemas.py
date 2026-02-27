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
