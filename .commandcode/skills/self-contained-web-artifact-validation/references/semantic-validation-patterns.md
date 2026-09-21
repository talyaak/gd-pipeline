# Semantic Validation Patterns for Static Analysis

## Context

The execution harness (Playwright + Chromium) performs semantic validation by checking:
- Active gameplay scene exists (scene key contains 'play' or 'game')
- Score registry initialized: `game.registry.set('score', 0)` after `window.__GAME__ = game`
- Active gameplay proof: `this.game.registry.inc('score', 1)` in `update()` OR `this.game.sessionTime` tracking in `update()`

These checks only run during browser execution (slow, ~27s). Adding them to static validation (fast, ~ms) catches failures early and provides actionable feedback to the codegen LLM.

## Patterns to Check

### 1. Scene Key Identification

```python
scene_class_match = re.search(r'class\s+(\w+)\s+extends\s+Phaser\.Scene', script)
if scene_class_match:
    scene_constructor_match = re.search(rf'class\s+{scene_class_match.group(1)}\s+extends\s+Phaser\.Scene\s*\{[^}]*super\([\'"]([\'"]+)[\'"]\)', script, re.DOTALL)
    if scene_constructor_match:
        scene_key = scene_constructor_match.group(1).lower()
        if 'play' not in scene_key and 'game' not in scene_key:
            issues.append(f"Main scene key '{scene_constructor_match.group(1)}' must include 'play' or 'game' for semantic validation (use 'PlayScene')")
else:
    issues.append("No Phaser.Scene class found")
```

### 2. Score Registry Initialization

```python
if 'window.__GAME__' in script:
    if 'game.registry.set' not in script and 'registry.set' not in script:
        issues.append("Missing game.registry.set('score', 0) after window.__GAME__ = game; — required for semantic validation")
```

### 3. Active Gameplay Proof (at least one required)

```python
has_score_increment = 'registry.inc' in script
has_session_time = 'sessionTime' in script
if 'update(' in script:
    if not has_score_increment and not has_session_time:
        issues.append("Missing both this.game.registry.inc('score', 1) and this.game.sessionTime tracking in update() — at least one is required for semantic validation to prove active gameplay/engagement")
```

## Integration with Review Prompt

When semantic validation fails at execution time, pass console errors to the review LLM:

```python
console_errors = exec_artifact.get("console_errors", [])
if console_errors:
    console_errors_section = f"- Console errors: {', '.join(console_errors)}"
else:
    console_errors_section = ""

prompt = PROMPT.format(..., console_errors_section=console_errors_section, ...)
```

This allows the review LLM to provide targeted feedback on semantic validation failures instead of generic "game doesn't work" responses.

## Benefits

| Metric | Before | After |
|--------|--------|-------|
| Feedback latency | ~27s (browser) | ~50ms (regex) |
| LLM rework guidance | Generic | Specific (missing registry.set, etc.) |
| Pipeline efficiency | Many execution cycles | Fewer cycles, faster convergence |

## Applicability

This pattern applies to any self-contained HTML5 artifact where:
- Execution harness has semantic requirements
- Those requirements manifest as detectable code patterns
- Fast static feedback improves LLM rework quality