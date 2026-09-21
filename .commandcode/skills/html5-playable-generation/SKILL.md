---
name: html5-playable-generation
description: Generate self-contained HTML5 playables with validation. Use when generating single-file HTML5 games — covers CDN vendoring, Playwright browser validation, LLM structured-output handling, semantic/engagement validation, variant generation, and gzip size gates.
---

# HTML5 Playable Generation Pipeline

## Overview
Patterns for building pipelines that generate **self-contained, deployment-ready HTML5 playables** from game concepts. Critical requirement: zero external dependencies at runtime (no CDN, no asset files, no network calls).

## Core Architecture

### Pipeline Topology (LangGraph)
```
research → design → spec → codegen → validate_execute → review
         ↑                    ↓              ↑
         └─────── rework ─────┘              └──── retry ────┘
```

### Key Stages
| Stage | Purpose | Validation |
|-------|---------|------------|
| `research` | Genre analysis (mechanics, juice, progression) | Structured JSON output |
| `design` | Game Design Document (GDD) | Human review gate optional |
| `spec` | Implementation spec (entities, state machine, balance) | Deterministic schema |
| `codegen` | Single HTML file with Phaser 3 | Static analysis + browser execution |
| `validate_execute` | Real browser test (Playwright) | Canvas renders, input responds, no console errors |
| `review` | LLM scores spec fidelity (1-10) | Score ≥7 passes |

## Critical Patterns

### 1. Zero-CDN Self-Containment
**Problem**: Generated games load Phaser from jsDelivr → fail in ad-network WebViews (no external network).

**Solution**:
- Vendor `phaser.min.js` at build time (`pipeline/vendor/phaser.min.js`)
- Inject inline at serve time in execution harness:
```python
PHASER_JS = (VENDOR_DIR / "phaser.min.js").read_text()
html = html.replace("</head>", f"<script>{PHASER_JS}</script></head>")
```
- Block ALL external requests in validation:
```python
context.route("**/*", lambda route: route.abort()
               if route.request.url.startswith("http") and "127.0.0.1" not in route.request.url
               else route.continue_())
```
- Update codegen prompt: \"Phaser 3 is PRELOADED as global `Phaser`. Do NOT include `<script src=\\\"...\\\">` tags.\"

**CSP Validation for Vendored Libraries**:
When vendoring JavaScript libraries, check for Content Security Policy (CSP) violations:
1. Search for `new Function(` or `eval(` patterns - common sources of CSP violations
2. The `new Function(\\\"return this\\\")` pattern used for globalThis polyfills violates strict CSP
3. Fix by replacing with `return globalThis` (modern browsers support globalThis directly)
4. After fixing, verify the library still works and rebuild if necessary
5. Test with CSP-enabled environments to confirm the violation is resolved
6. **Feature-specific assessment**: Some libraries contain CSP-violating code for optional features your generated content may not use. Before fixing, audit your generated output to confirm whether the feature is actually needed:
   - Search for usage patterns in generated game code (e.g., `this.load.sceneFile` for Phaser's SceneFile loader)
   - If the feature is unused, consider replacing the problematic code with a clear error message rather than attempting to make it CSP-compliant
   - Example: In Phaser's SceneFile loader, we replaced `addToCache` with `throw new Error('SceneFile loader is not available in CSP-compatible build.')` after confirming generated games use only procedural asset creation
   - Always verify the library still builds and that your generated content remains unaffected

### 2. Static Validation Gates
Add to `validate.py`:
```python
EXTERNAL_SCRIPT_TAG = re.compile(r'<script\s+src\s*=\s*["\']https?://', re.IGNORECASE)
NETWORK_API_CALLS = ["fetch(", "XMLHttpRequest", "WebSocket(", "navigator.sendBeacon"]

if EXTERNAL_SCRIPT_TAG.search(html):
    issues.append("Contains external <script src=\"http...\"> tag")

for api in NETWORK_API_CALLS:
    if api in script:
        issues.append(f"Uses network API '{api}' — no external network access allowed")
```

### 3. LLM Structured Output with Fallbacks
OpenRouter/Claude doesn't always honor `with_structured_output`. Use JSON parsing with fallback:

### 4. Semantic Gameplay Validation
Static + browser execution only proves "loads + renders + input changes." Add behavioral assertions and engagement metrics:

```python
# In execute.py after input interaction:
semantic_ok = True
try:
    game_exposed = page.evaluate("() => typeof window.__GAME__ !== 'undefined'")
    if not game_exposed:
        console_errors.append("Semantic validation: window.__GAME__ not exposed")
        semantic_ok = False
    else:
        # Check active gameplay scene
        scene_active = page.evaluate("() => window.__GAME__.scene.isActive('Play') || window.__GAME__.scene.isActive('GameScene') || window.__GAME__.scene.isActive('MainScene')")
        if not scene_active:
            console_errors.append("Semantic validation: no active gameplay scene")
            semantic_ok = False
        
        # Check score registry
        has_score = page.evaluate("() => window.__GAME__.registry.has('score')")
        if has_score:
            score_val = page.evaluate("() => window.__GAME__.registry.get('score')")
            if not isinstance(score_val, (int, float)) or score_val < 0:
                console_errors.append("Semantic validation: invalid score value")
                semantic_ok = False
        
        # Check not game-over immediately
        game_over = page.evaluate("() => window.__GAME__.registry.get('gameOver') === true")
        if game_over:
            console_errors.append("Semantic validation: game over immediately")
            semantic_ok = False
            
        # Additional semantic checks can be added here (e.g., win state detection)
except Exception as exc:
    console_errors.append(f"Semantic validation error: {exc}")
    semantic_ok = False

# Measure engagement duration and completion rate
engagement_duration_ms = None
completion_rate = None
try:
    # Extend observation period to measure engagement (e.g., 20 seconds)
    engagement_start_time = None
    engagement_end_time = None
    total_engagement_ms = 0
    win_state_detected = False
    
    # Observe for extended period to measure engagement
    observation_end = time.time() + 20.0  # 20 seconds observation
    while time.time() < observation_end:
        # Check game state to determine if we're in an active play state
        try:
            game_state_info = page.evaluate("""() => {
                const game = window.__GAME__;
                if (!game) return { state: 'unknown', reason: 'no game' };
                
                // Check for common state properties
                if (game.state !== undefined) {
                    return { state: game.state, reason: 'game.state' };
                }
                
                // Check for scene-based states (Phaser)
                if (game.scene && game.scene.scenes) {
                    const activeScenes = game.scene.scenes.filter(s => s.visible && s.active);
                    if (activeScenes.length > 0) {
                        // Map common scene names to states
                        const sceneNames = activeScenes.map(s => s.settings.key.toLowerCase());
                        if (sceneNames.some(name => ['play', 'game', 'level'].includes(name))) {
                            return { state: 'playing', reason: 'phaser scene' };
                        }
                        if (sceneNames.some(name => ['menu', 'main', 'start'].includes(name))) {
                            return { state: 'menu', reason: 'phaser scene' };
                        }
                        if (sceneNames.some(name => ['gameover', 'game over', 'over'].includes(name))) {
                            return { state: 'gameover', reason: 'phaser scene' };
                        }
                        if (sceneNames.some(name => ['win', 'won', 'victory', 'success'].includes(name))) {
                            return { state: 'win', reason: 'phaser scene' };
                        }
                        return { state: activeScenes[0].settings.key.toLowerCase(), reason: 'phaser scene' };
                    }
                }
                
                // Check registry for game over flag (common in many games)
                if (game.registry && typeof game.registry.get === 'function') {
                    try {
                        const gameOver = game.registry.get('gameOver');
                        if (gameOver === true) {
                            return { state: 'gameover', reason: 'registry.gameOver' };
                        }
                    } catch(e) {/* ignore */ }
                }
                
                // Check for score increasing as a sign of active play
                if (game.registry && typeof game.registry.get === 'function') {
                    try {
                        const score = game.registry.get('score');
                        if (typeof score === 'number' && score > 0) {
                            return { state: 'playing', reason: 'score > 0' };
                        }
                    } catch(e) {/* ignore */ }
                }
                
                return { state: 'unknown', reason: 'no recognizable state' };
            }""")
            
            current_state = game_state_info.get('state', 'unknown')
            
            # Track engagement: consider 'playing' states as engaged
            is_engaged = current_state in ['playing', 'play', 'game', 'level']
            
            if is_engaged and engagement_start_time is None:
                engagement_start_time = time.time()
            
            if not is_engaged and engagement_start_time is not None and engagement_end_time is None:
                engagement_end_time = time.time()
                
            # Check for completion states
            if current_state in ['win', 'won', 'victory', 'success']:
                win_state_detected = True
            elif current_state in ['gameover', 'game over', 'over'] and engagement_start_time is not None:
                # Game over after having played = completed a session
                pass  # Will count as completed if we had engagement
                
        except Exception as e:
            # If we can't read game state, assume we're still engaged if we were before
            pass
        
        page.wait_for_timeout(500)  # Check every 500ms
    
    # If we started engagement but never ended it, set end time to now
    if engagement_start_time is not None and engagement_end_time is None:
        engagement_end_time = time.time()
    
    # Calculate total engagement time
    if engagement_start_time is not None and engagement_end_time is not None:
        total_engagement_ms = int((engagement_end_time - engagement_start_time) * 1000)
    
    # For completion rate, if we detected a win state, it's 1.0
    # If we had significant engagement, calculate based on time vs target session
    if win_state_detected:
        completion_rate = 1.0
    elif total_engagement_ms > 0:
        # Calculate completion rate based on engagement time vs target session (30s)
        target_session_ms = 30 * 1000  # 30 seconds
        completion_rate = min(total_engagement_ms / target_session_ms, 1.0)
    else:
        completion_rate = 0.0
        
    engagement_duration_ms = total_engagement_ms if total_engagement_ms > 0 else None
    # Note: completion_rate is always set (0.0 to 1.0)
    
except Exception as exc:
    # Don't fail the whole execution if metrics collection fails
    pass
```

**Codegen prompt requirement**: "Expose the Phaser.Game instance as `window.__GAME__` immediately after creation (e.g. `window.__GAME__ = game;`). Initialize `game.registry.set('score', 0)` and `game.registry.set('gameOver', false)`. For engagement tracking, games should update score or state to indicate active play."

### 5. Reskin / Parametrize Layer (ONDEMAND_GENERATION.md)

Per STRATEGY.md pivot (2026-09-02): generation only handles reskin/parameters on top of proven-fun hand-built harnesses.

**Architecture:**
```
brief.json (per-request) → manifest.json (per-harness schema) → reskin.py → build_harness_html.sh (SRC_GAME_JS override) → Playwright validation
```

**Key components:**
- `pipeline/reskin.py` — validates brief against manifest, substitutes const values in harness .game.js
- `harness/<genre>.manifest.json` — defines valid params (int ranges, color_array counts), copy_slots, asset_slots
- `scripts/build_harness_html.sh` — enhanced with 3rd arg `SRC_GAME_JS` for reskin builds
- Output isolation: reskin HTML goes to `harness/<genre>_reskinned/`, **never** overwrites master

**Validated:** match_3 reskin passes execution validation (loaded, canvas, input, no errors, engagement ~20s).

**Gate:** Block-assembly mode gated until reskin works for 2-3 genres end-to-end.

### 5. Variant Generation (Post-Review)
After a game passes all validation, generate deterministic variants cheaply:

```python
def variant_gen(state: RunState) -> dict:
    base_html = state["code"]["artifact"]["html"]
    
    variant_configs = [
        {"type": "palette", "name": "neon"},
        {"type": "palette", "name": "retro"},
        {"type": "palette", "name": "pastel"},
        {"type": "difficulty", "name": "easy"},
        {"type": "difficulty", "name": "hard"},
        {"type": "cta", "name": "install"},
        {"type": "cta", "name": "play"},
        {"type": "theme", "name": "particle_trails"},
    ]
    
    variants = _generate_variants(base_html, spec, variant_configs)
    
    # Validate each variant through static + execution gates only
    # Skip research/design/spec/review - reuses validated base
    results = []
    for variant in variants:
        static_issues = check_html_game(variant["html"])
        if static_issues:
            results.append({**variant, "status": "failed_static", "errors": static_issues})
            continue
        
        report = run_execution_report(variant["html"], variant_dir)
        runtime_ok = report.loaded and not report.console_errors and report.canvas_rendered
        results.append({**variant, "status": "passed" if runtime_ok else "failed_runtime"})
    
    return {"variants": {"status": "passed" if any(r["status"] == "passed" for r in results) else "failed", "artifact": {"variants": results}}}
```

**Transformation types:**
| Type | Examples | Cost |
|------|----------|------|
| Palette swap | neon, retro, pastel, mono | ~0 tokens |
| Difficulty | easy, hard, insane | ~0 tokens |
| CTA injection | install, play, signup | ~0 tokens |
| Visual theme | particle_trails, glow, minimal | ~0 tokens |

### 6. Size Gate (Post-Static, Pre-Browser)
```python
# validate_execute.py
import gzip
MAX_GZIP_SIZE_KB = 500

def validate_execute(state: RunState) -> dict:
    html = state["code"]["artifact"]["html"]
    
    # ... static checks ...
    
    gzipped_html = gzip.compress(html.encode("utf-8"))
    gzip_size_kb = len(gzipped_html) / 1024
    if gzip_size_kb > MAX_GZIP_SIZE_KB:
        return {"status": "failed_needs_rework", "error": f"Gzipped HTML size ({gzip_size_kb:.1f} KB) exceeds limit ({MAX_GZIP_SIZE_KB} KB)"}
    
    # ... browser execution ...
```

```python
def research(state: RunState) -> dict:
    llm = get_review_llm()
    raw = invoke_with_retry(lambda: llm.invoke(PROMPT.format(brief=state["brief"])))
    content = raw.content if hasattr(raw, "content") else str(raw)
    
    try:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
        else:
            raise ValueError("No JSON found")
    except Exception:
        data = DEFAULT_FALLBACK
    
    # Normalize: ensure strings are strings, lists are lists
    if isinstance(data.get("progression"), list):
        data["progression"] = " ".join(data["progression"])
    
    return {"research": {"status": "passed", "artifact": GenreAnalysis(**data).model_dump()}}
```

**Apply to all LLM nodes**: `research`, `design`, `spec`, `review`.

### 4. Test Fixture Hygiene
When validation rules change, update fixtures:
- `known_good_game.html` — must pass ALL static checks (no CDN, no asset refs)
- `known_bad_game_*.html` — must fail specific checks (asset ref, deltaTime, etc.)

## Pitfalls & Gotchas

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| CDN allowlist in harness | False positives | Remove `cdn.jsdelivr.net` from route allowlist |
| LLM returns dict for `progression` | Pydantic validation error | Normalize: `if isinstance(v, list): v = " ".join(v)` |
| `with_structured_output` fails | `pop from empty list` in tests | Add JSON parsing fallback in `_FakeLLM.invoke()` |
| Phaser not in saved artifact | `ReferenceError: Phaser is not defined` | Create standalone with Phaser inlined |
| Token budget too low | Truncated game code | Set `CODEGEN_MAX_TOKENS=48000` |

## Verification Checklist
- [ ] All 20+ tests pass
- [ ] Generated HTML has NO `<script src="http...">` tags
- [ ] Static validation passes
- [ ] Browser execution: canvas renders, input responds, zero console errors
- [ ] LLM review score ≥7
- [ ] Artifact runs standalone via `file://` or static server
- [ ] Size gate passes (gzipped < 500KB)
- [ ] Semantic validation passes (window.__GAME__ exposed, active scene, score registry)
- [ ] Engagement duration metrics collected (non-negative milliseconds or null)
- [ ] Completion rate metrics collected (float between 0.0 and 1.0)

## Structured Error Taxonomy (from playable-ad pipeline)

Classify failures for targeted rework instead of generic retries:

| Category | When | Recovery |
|----------|------|----------|
| `TRANSIENT` | Network, rate limit, timeout | Retry with exponential backoff |
| `TRUNCATION` | Hit max_tokens | Increase limit or shorten prompt |
| `SYNTAX` | Invalid HTML/JS, schema violation | Fix prompt structure |
| `SEMANTIC` | Wrong game logic, score registry, scene state | Fix game logic |
| `VALIDATION` | Asset refs, deltaTime naming, external scripts | Fix codegen output |

## Per-Node Configuration (from playable-ad pipeline)

```python
NODE_TIMEOUTS = {
    "research": 60, "design": 60, "spec": 60,
    "codegen": 180, "validate_execute": 120,
    "review": 60, "variant_gen": 180,
}

NODE_MAX_ATTEMPTS = {
    "research": 2, "design": 3, "spec": 2,
    "codegen": 3, "validate_execute": 2,
    "review": 2, "variant_gen": 1,
}
```

Tune these against observed failure modes; timeouts set too short get misdiagnosed as rate-limit failures (see the `langgraph-debugging` skill, Pattern 7).

## References
- `references/phaser-vendoring.md` — Phaser version selection, size optimization
- `references/llm-json-parsing.md` — Fallback patterns for structured output
- `references/validation-gates.md` — Static + dynamic validation composition
- `references/engagement-metrics.md` — Engagement duration and completion rate metrics
- `templates/playable-ad-pipeline/` — Starter LangGraph pipeline structure