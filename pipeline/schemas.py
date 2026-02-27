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
