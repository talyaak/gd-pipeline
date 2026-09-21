---
name: self-contained-web-artifact-validation
description: Validate self-contained HTML5 artifacts via runtime vendoring plus static/execution/semantic/review gates. Use when generating single-file HTML5 for no-network deployment (ad-network WebViews, offline bundles), or when generated games pass validation but black-screen in production.
---

# Self-Contained Web Artifact Validation

## Problem

Generated HTML5 artifacts often depend on external CDNs for runtime libraries (Phaser, Three.js, etc.). This works in development but **fails in production** when deployed to ad-network WebViews or any environment blocking external network requests.

**Empirical finding**: Every generated game became a black screen when CDN access was blocked, because the validation harness allowed the CDN domain — producing false positives.

## Solution Pattern

### 1. Vendor Runtime Dependencies at Build Time

```bash
mkdir -p pipeline/vendor
curl -sL "https://cdn.jsdelivr.net/npm/phaser@3.80.1/dist/phaser.min.js" \
  -o pipeline/vendor/phaser.min.js
```

### 2. Inject at Validation Runtime

The generator should **not** include `<script src="...">` tags. The validation harness injects the vendored library:

```python
PHASER_JS = (VENDOR_DIR / "phaser.min.js").read_text(encoding="utf-8")

def run_execution_report(html: str, out_dir: Path) -> ExecutionReport:
    if "</head>" in html:
        html = html.replace("</head>", f"<script>{PHASER_JS}</script></head>")
    else:
        html = html.replace("<body>", f"<body><script>{PHASER_JS}</script>")
```

### 3. Update Generator Prompts

> "Phaser 3 is PRELOADED as a global `Phaser` variable. Do NOT include any `<script src="...">` tags. Write only your game code."

### 4. Block ALL External Network in Validation

```python
context.route("**/*", lambda route: route.abort()
               if route.request.url.startswith("http") and "127.0.0.1" not in route.request.url
               else route.continue_())
```

### 5. Add Static Validation Gates

```python
EXTERNAL_SCRIPT_TAG = re.compile(r'<script\\s+src\\s*=\\s*[\"\\']https?://', re.IGNORECASE)
NETWORK_API_CALLS = ["fetch(", "XMLHttpRequest", "WebSocket(", "navigator.sendBeacon"]

def check_html_game(html: str) -> list[str]:
    issues = []
    if EXTERNAL_SCRIPT_TAG.search(html):
        issues.append("Contains external <script src=\"http...\"> tag")
    for api in NETWORK_API_CALLS:
        if api in script:
            issues.append(f"Uses network API '{api}' — no external network access allowed")
    return issues
```

### 5b. Extend Static Gate with Semantic Validation Requirements

Catch semantic validation failures at static-analysis time — before browser launch — by checking for patterns the execution harness requires:

```python
# 1. Main gameplay scene key must be identifiable (e.g., 'PlayScene' or containing 'play'/'game')
scene_class_match = re.search(r'class\\s+(\\w+)\\s+extends\\s+Phaser\\.Scene', script)
if scene_class_match:
    scene_constructor_match = re.search(rf'class\\s+{scene_class_match.group(1)}\\s+extends\\s+Phaser\\.Scene\\s*\\{{[^}}]*super\\([\\'\"]([^\\'\"]+)[\\'\"]\\)', script, re.DOTALL)
    if scene_constructor_match:
        scene_key = scene_constructor_match.group(1).lower()
        if 'play' not in scene_key and 'game' not in scene_key:
            issues.append(f"Main scene key '{scene_constructor_match.group(1)}' must include 'play' or 'game' for semantic validation (use 'PlayScene')")
else:
    issues.append("No Phaser.Scene class found")

# 2. Score registry initialization after window.__GAME__ = game
if 'window.__GAME__' in script:
    if 'game.registry.set' not in script and 'registry.set' not in script:
        issues.append("Missing game.registry.set('score', 0) after window.__GAME__ = game; — required for semantic validation")

# 3. At least one of: score increment in registry OR session time tracking in update()
has_score_increment = 'registry.inc' in script
has_session_time = 'sessionTime' in script
if 'update(' in script:
    if not has_score_increment and not has_session_time:
        issues.append("Missing both this.game.registry.inc('score', 1) and this.game.sessionTime tracking in update() — at least one is required for semantic validation to prove active gameplay/engagement")
```

This shifts semantic validation failures left — caught by fast static regex instead of slow browser execution.

### 6. Three-Gate Validation Pipeline

| Gate | Purpose | Tool |
|------|---------|------|
| **Static** | Syntax, banned patterns, external refs | Regex + `node --check` |
| **Execution** | Loads, renders canvas, responds to input | Playwright + headless Chromium |
| **Semantic** | Game logic works (score, win/lose, active scene) | Playwright evaluate assertions |
| **Review** | Spec fidelity, code quality | LLM judge (score ≥ 7) |

### 7. Evidence Preservation

Save every attempt's artifacts to disk (not overwritten):
```
output/<run>/<NN>_<stage>/attempt_<N>/
  game.html
  execution.json
  review.json
```

## Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| CDN allowlist in harness | False positives in CI | Remove allowlist; inject vendored lib |
| Generator emits CDN tags | Passes locally, fails in prod | Prompt: "Phaser is preloaded, no script tags" |
| Structured output fails on OpenRouter | `400 Bad Request` | Parse JSON from plain text response |
| Balance values as numbers | Pydantic validation error | Normalize: `str(value)` for all balance entries |
| `progression` as array | Schema expects string | Join array: `" ".join(data["progression"])` |
| Vendor injection into self-contained HTML | "Identifier already declared" errors; `window.__GAME__` detection breaks | Detect bundled Phaser/Juice via `_has_vendor_scripts()` and skip injection for self-contained artifacts |

## OpenRouter Integration Pattern

When using OpenRouter with Anthropic models, structured output may not work:

```python
llm = get_review_llm()  # ChatOpenAI with base_url="https://openrouter.ai/api/v1"
raw = llm.invoke(prompt)
content = raw.content if hasattr(raw, "content") else str(raw)
start = content.find("{")
end = content.rfind("}") + 1
if start >= 0 and end > start:
    data = json.loads(content[start:end])
else:
    data = fallback_data
result = SchemaClass(**data)
```

## Applicability Beyond Games

This pattern applies to any single-file HTML5 artifact:
- Playable ads (MRAID, VAST wrappers)
- Interactive widgets (calculators, configurators)
- Data visualizations (D3, Chart.js vendored)
- Offline-first PWAs

## References

- [`references/semantic-validation-patterns.md`](references/semantic-validation-patterns.md) — Static checks for semantic validation requirements
- [`references/phaser-vendoring.md`](references/phaser-vendoring.md) — Phaser download and version pinning
- [`references/self-contained-html-handling.md`](references/self-contained-html-handling.md) — Detecting and handling pre-bundled HTML in validation harness
- [`references/cdn-trap-case-study.md`](references/cdn-trap-case-study.md) — Case study from gd-pipeline: how a CDN allowlist hid a Phaser dependency, empirical reproduction steps, and the fix