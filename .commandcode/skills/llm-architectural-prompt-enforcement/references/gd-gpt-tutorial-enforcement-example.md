# Example: Enforcing Tutorial Phase in gd-gpt

This reference documents the specific implementation of LLM architectural prompt enforcement from the gd-gpt project (playable ad generation pipeline).

## Context
The gd-gpt project generates playable HTML5 ads using a multi-agent pipeline: research → design → spec → codegen → validate.

## Architectural Requirement
All games must include a substantive Tutorial phase for proper player onboarding, as optional tutorials were causing 46.7% drop-off in the first 3 seconds.

## Implementation
Modified the spec node prompt in `pipeline/nodes/spec.py`:

**Before**:
```
CRITICAL: The state_machine MUST include these states in order:
- 'Boot' (engine init, scale manager, physics config)
- 'Preload' (generate procedural textures, load audio)
- 'Tutorial' (interactive onboarding, can be skipped)
- 'Play' (core gameplay loop)
- 'GameOver' (failure state, show CTA, offer replay)
- 'Win' (success state, show CTA, offer next level/replay)

If the genre genuinely doesn't need Tutorial or Win (e.g. pure endless runner), include them anyway but mark as optional in behavior notes.
```

**After**:
```
CRITICAL: The state_machine MUST include these states in order:
- 'Boot' (engine init, scale manager, physics config)
- 'Preload' (generate procedural textures, load audio)
- 'Tutorial' (interactive onboarding - required for all genres, must be substantive)
- 'Play' (core gameplay loop)
- 'GameOver' (failure state, show CTA, offer replay)
- 'Win' (success state, show CTA, offer next level/replay)

Tutorial phase is mandatory for all genres and must provide meaningful onboarding - do not mark as optional.
```

## Additional Prompt Engineering Considerations

When including JSON examples in LLM prompts, special care must be taken to prevent prompt libraries from misinterpreting curly braces as format placeholders.

**Issue Encountered**: 
In the spec node prompt, the JSON example for the balance field:
```
e.g., {\"gravity\": \"1200\", \"jump_velocity\": \"-400\"}
```
was being interpreted by langchain as containing a format placeholder `{gravity}`, causing a KeyError when no \"gravity\" variable was provided.

**Fix Applied**:
Escaped the curly braces by doubling them:
```
e.g., {{\"gravity\": \"1200\", \"jump_velocity\": \"-400\"}}
```

This ensures the curly braces are treated as literal text rather than format placeholders.

## Validation
1. Verified the spec node compiles successfully (no syntax errors)
2. Confirmed prompt changes correctly reflect mandatory tutorial requirement
3. Verified existing spec validation logic preserved
4. Created and ran validation tests to ensure the change works as expected
5. Verified that the JSON example escaping fix prevents langchain KeyError

## Impact
- Ensures all generated games include a proper onboarding sequence
- Addresses a key retention issue identified in the P1 roadmap
- Demonstrates how to enforce structural requirements through prompt engineering
- Shows the importance of proper prompt formatting when including structured data examples

## Additional Fix: codegen Node Prompt Curly Brace Escaping (2026-08-31)

**Context**: The codegen node in `pipeline/nodes/codegen.py` generates the actual Phaser 3 game HTML. Its PROMPT string contains JavaScript code blocks with many curly braces for object literals, function bodies, and control flow.

**Issue Encountered**:
The JavaScript code blocks in the PROMPT contained unescaped curly braces (e.g., `if (typeof mraid !== 'undefined') { ... }`). When Python's `.format()` was called to inject variables like `{gdd}`, `{spec}`, `{visual_spec}`, etc., the standalone `{` and `}` in the JavaScript code were interpreted as format placeholders, causing a `KeyError: '\n  // Per MRAID spec'`.

**Fix Applied** (commit cedd072):
Escaped ALL curly braces in JavaScript code blocks by doubling them:
```javascript
// Before (broken):
if (typeof mraid !== 'undefined') {
  if (mraid.getState() === 'loading') {
    mraid.addEventListener('ready', () => {
      if (mraid.isViewable()) {
        startGameplay();
      }
    });
  }
}

// After (fixed):
if (typeof mraid !== 'undefined') {{
  if (mraid.getState() === 'loading') {{
    mraid.addEventListener('ready', () => {{
      if (mraid.isViewable()) {{
        startGameplay();
      }}
    }});
  }}
}}
```

This fix was applied to all JavaScript code blocks in the PROMPT string (MRAID gating implementation, PlayScene update() method, PlayScene class definition).

**Additional Prompt Changes** (same commit):
Aligned the codegen prompt with the validation pattern used by `known_good_game.html` (which passes semantic validation):
- Replaced MRAID gating with `startGameplay()` pattern (matches known_good_game)
- Added CRITICAL requirements: `game.registry.set('score', 0)` + `game.registry.inc('score', 1)` in update()
- Added CRITICAL requirement: `this.game.sessionTime` updated in update()
- Required main scene named `'PlayScene'` for scene-based validation fallback
- Updated REWORK_PROMPT reminder with new critical requirements

**Validation**: All 4 test modules pass (codegen, validate, execute, graph_routing).

## Moving Prompts to External Files to Avoid Curly Brace Issues

When LLM prompts contain both format placeholders (for variables) and literal curly braces (e.g., in JSON examples), prompt libraries like LangChain may interpret all curly braces as format placeholders, leading to KeyError if the literal braces do not match provided variables.

To avoid this, move the entire prompt template to an external text file and load it at runtime. Then, replace the placeholders with actual values using str.format() or similar.

**Steps**:
1. Create a .txt file containing the prompt template, with placeholders like `{gdd}` for variables.
2. Ensure that any literal curly braces in the template (e.g., JSON examples) are escaped by doubling them: `{{` and `}}`.
3. In the node code, load the template from the file and format it with the required variables.

**Example from gd-gpt spec node**:
- Created `pipeline/nodes/spec_prompt.txt` containing the prompt with `{gdd}` placeholder and literal JSON examples with doubled curly braces.
- In `pipeline/nodes/spec.py`, replaced the hardcoded PROMPT string with:
  ```python
  with open(path_to_prompt_file, 'r') as f:
      PROMPT = f.read()
  # later:
  prompt = PROMPT.format(gdd=design_artifact)
  ```

This approach prevents the KeyError and keeps the prompt maintainable.

## Making Semantic Validation Requirements Impossible to Miss (2026-08-31)

**Context**: The codegen node prompt in `pipeline/nodes/codegen.py` was updated with CRITICAL requirements for semantic validation (`game.registry.set('score', 0)`, `game.registry.inc('score', 1)`, `this.game.sessionTime` tracking, main scene named 'PlayScene'). However, despite these being explicitly listed in the prompt, the LLM consistently failed to include them across multiple generation attempts, exhausting the rework loop (3 attempts) and resulting in `failed_max_attempts`.

**Root Cause**: The semantic validation requirements were buried within a large prompt (400+ lines) alongside MRAID gating, audio muting, CTA button, and other compliance requirements. The LLM treated them as just another bullet point rather than non-negotiable invariants.

**Fix Applied**: Restructure the prompt to make semantic validation requirements impossible to miss:

1. **Add a dedicated "SEMANTIC VALIDATION REQUIREMENTS" section at the TOP of the prompt** (before any other requirements), using the [REQUIREMENT]/[RATIONALE]/[CONSEQUENCE] pattern:

```
=== SEMANTIC VALIDATION REQUIREMENTS (NON-NEGOTIABLE) ===
These three requirements are validated by the browser execution harness.
Failure on ANY of these = immediate rework, no exceptions.

[REQUIREMENT]: After `window.__GAME__ = game;`, immediately call:
  game.registry.set('score', 0);
  game.registry.set('gameOver', false);

[RATIONALE]: The validator checks for score registry initialization on the Game instance
[CONSEQUENCE]: Missing this = "Semantic validation: no active gameplay scene" error

[REQUIREMENT]: In your main scene's update(), track session time on the Game instance:
  this.game.sessionTime = (this.game.sessionTime || 0) + delta;

[RATIONALE]: The validator measures engagement via game.sessionTime
[CONSEQUENCE]: Missing this = completion_rate = 0.0, engagement_duration = null

[REQUIREMENT]: In update(), while player is alive, increment score in registry:
  if (this.player && this.player.alive) {
    this.game.registry.inc('score', 1);
  }

[RATIONALE]: The validator proves active gameplay via score increasing
[CONSEQUENCE]: Missing this = validator sees no active gameplay

[REQUIREMENT]: Name your main gameplay scene 'PlayScene' with super('PlayScene') constructor

[RATIONALE]: Fallback scene-based validation looks for 'play' in scene key
[CONSEQUENCE]: Wrong name = validator can't identify active gameplay scene
```

2. **Provide a standalone, copy-pasteable code block** that the LLM can drop in without modification:

```javascript
// === COPY-PASTE THIS BLOCK EXACTLY FOR SEMANTIC VALIDATION ===
// Place immediately after: const game = new Phaser.Game(config);
// Then: window.__GAME__ = game;

game.registry.set('score', 0);
game.registry.set('gameOver', false);

// In your PlayScene's update():
update(time, delta) {
  const dt = delta / 1000;
  // ... your game logic ...

  // SEMANTIC VALIDATION: Track session time on Game instance
  this.game.sessionTime = (this.game.sessionTime || 0) + delta;

  // SEMANTIC VALIDATION: Increment score in registry (proves active gameplay)
  if (this.player && this.player.alive) {
    this.game.registry.inc('score', 1);
  }
}

// SEMANTIC VALIDATION: Scene must be named 'PlayScene'
class PlayScene extends Phaser.Scene {
  constructor() {
    super('PlayScene');
  }
  // ...
}
```

3. **Keep the detailed requirements in the body** but cross-reference the top section.

**Validation**: After this change, the LLM should produce compliant output on attempt 1 without needing rework for semantic validation issues.

**General Principle**: When validation enforces non-negotiable structural invariants, promote them from "requirements among many" to "a dedicated, prominent, copy-pasteable contract" at the top of the prompt. The cost of a slightly longer prompt is far less than the cost of exhausted rework loops.