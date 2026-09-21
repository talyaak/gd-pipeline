# Anti-Pattern Documentation in Codegen Prompt (gd-gpt)

## Context

In the gd-gpt playable ad pipeline, the codegen node was consistently producing games that passed browser execution but failed LLM review (score 6/10 vs threshold 7). Root cause analysis showed recurring spec fidelity issues:

1. Wrong scene name (e.g., 'GameScene' instead of 'PlayScene')
2. Hardcoded session duration (30s instead of template variables)
3. Wrong delta-time variable name ('elapsedTime' instead of 'dt')
4. Missing sessionTime tracking on Game instance
5. Missing score increment in registry
6. CTA button created lazily instead of in create()
7. Calling `mraid.ready()` instead of listening for ready event

## Solution

Added an explicit "COMMON MISTAKES THAT CAUSE REVIEW FAILURES — DO NOT DO THESE" section to the codegen prompt in `pipeline/nodes/codegen.py` (commit dbbf9ba). This section lists each anti-pattern with a clear prescription of what to do instead.

## Pattern

```python
COMMON MISTAKES THAT CAUSE REVIEW FAILURES — DO NOT DO THESE:
- WRONG SCENE NAME: The main gameplay scene MUST be named exactly 'PlayScene' (super('PlayScene')). Do not use 'GameScene', 'MainScene', 'Play', or any other name.
- HARDCODED SESSION DURATION: Do NOT hardcode 30 seconds or any other duration. Use the template variables {tutorial_duration_seconds} and {target_session_seconds} exactly as provided in the spec.
- WRONG DELTA-TIME VARIABLE: In update(time, delta), the variable MUST be named 'dt' (const dt = delta / 1000;). Never use 'deltaTime', 'elapsed', or 'elapsedTime'.
- MISSING SESSION TIME TRACKING: You MUST update this.game.sessionTime in update() for validation: this.game.sessionTime = (this.game.sessionTime || 0) + delta;
- MISSING SCORE INCREMENT: You MUST increment score in registry while player is alive: this.game.registry.inc('score', 1);
- CTA BUTTON CREATED LAZILY: The CTA button (this.ctaButton) MUST be created in create() and setVisible(false) there. Only call setVisible(true) when the game ends. Do NOT create it inside the game-over/win/lose function.
- CALLING MRAID.READY(): Never call mraid.ready() — it is fired by the host bridge. Gate gameplay on mraid.addEventListener('ready', ...) + mraid.isViewable() instead.
```

## Why This Works

- **Positive framing**: Each item states what MUST be done, not just what to avoid
- **Concrete prescriptions**: Exact code patterns provided
- **Tied to consequences**: "causes review failures" signals non-negotiable
- **Prominent placement**: Near the top of the prompt, before the known-good pattern
- **Addresses observed failure modes**: Derived from actual review feedback, not speculation

## Validation

- All unit tests pass (codegen, validate, patch, graph_routing, review, pipeline_integration)
- Next cycle: run fresh pipeline to verify review score improves with this prompt change

## Generalization

This technique applies to any LLM agent in a pipeline where:
- Post-generation validation catches specific recurring errors
- Lowering quality thresholds is being considered as a "fix"
- The errors are structural/architectural rather than creative

Instead of lowering the bar, document the bar explicitly in the prompt.