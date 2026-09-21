# Validation Gates for Self-Contained Playables

## Three-Layer Validation

### 1. Static Analysis (validate.py)
Fast, deterministic, no browser needed. Runs first.

```python
# In check_html_game(html):
# - Doctype check
# - Banned delta-time names (deltaTime, elapsedTime, etc.)
# - Asset loader calls (load.image, load.audio, etc.)
# - Asset file extensions (.png, .jpg, .mp3, etc.)
# - Phaser.Game instantiation
# - update() method existence
# - JS syntax (node --check)
# - External script tags (NEW)
# - Network API calls (NEW)
```

### 2. Browser Execution (execute.py)
Real Playwright Chromium run. Catches runtime errors.

```python
# Blocks ALL external requests:
context.route("**/*", lambda route: route.abort()
               if route.request.url.startswith("http") and "127.0.0.1" not in route.request.url
               else route.continue_())

# Checks:
# - Page loads without crash
# - Zero console errors
# - Canvas rendered (width > 0, height > 0)
# - Input produces observable change (screenshot diff)
```

### 3. LLM Review (review.py)
Semantic fidelity scoring (1-10).

```python
# Prompt includes execution evidence:
# - Loaded cleanly: {loaded}
# - Canvas rendered: {canvas_rendered}
# - Input response: {input_response}
# - Full generated HTML

# Score ≥7 passes, else rework loop (max 2 attempts)
```

## Validation Pipeline Flow
```
codegen → static_validation
    ↓ pass
browser_execution
    ↓ pass
llm_review (score ≥7)
    ↓ pass
DONE
    ↓ fail (any stage)
rework loop → codegen (max 2 attempts)
```

## Adding New Static Checks
```python
# In validate.py, add to check_html_game():
NEW_CHECKS = [
    (pattern_or_callable, "Human-readable error message"),
]

for check, msg in NEW_CHECKS:
    if check(html) or check(script):
        issues.append(msg)
```

## Test Fixture Requirements
When adding checks, update fixtures:
- `known_good_game.html` — MUST pass all checks
- `known_bad_game_<check>.html` — MUST fail specific check