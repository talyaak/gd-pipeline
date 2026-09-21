# CDN Trap Case Study: gd-pipeline Phaser Dependency

## Context
The `gd-pipeline` project (predecessor to this playable-ad creator) generated HTML5 games using Phaser 3. The pipeline had a full validation chain:
- Static analysis (regex checks for asset loaders, banned delta-time names)
- Real browser execution via Playwright
- LLM code review for spec fidelity

All tests passed. The integration test used a "known good" fixture that loaded Phaser from CDN.

## The Trap
The Playwright execution harness at `execute.py` had this route handler:

```python
context.route("**/*", lambda route: route.abort()
               if route.request.url.startswith("http") and "127.0.0.1" not in route.request.url
               and "cdn.jsdelivr.net" not in route.request.url  # <-- ALLOWLIST
               else route.continue_())
```

The codegen prompt explicitly required:
```html
<script src="https://cdn.jsdelivr.net/npm/phaser@3/dist/phaser.min.js"></script>
```

The fixture `known_good_game.html` also loaded Phaser from CDN.

## Empirical Reproduction
When the CDN allowlist was removed (simulating an ad-network WebView with no external network access):
1. Every generated game became a black screen
2. Console error: `Phaser is not defined`
3. Canvas never rendered
4. All validation gates had previously passed — **false positives**

## Root Cause
The validation harness explicitly allowed the CDN domain, so the browser execution test never experienced the actual deployment environment's network restrictions.

## Fix Applied
1. **Vendored Phaser**: Downloaded `phaser.min.js` to `pipeline/vendor/`
2. **Removed CDN allowlist**: Changed route handler to block ALL external `http(s)://` requests
3. **Injected at serve time**: Execution harness injects vendored Phaser before `</head>`
4. **Updated generator prompt**: "Phaser 3 is PRELOADED as global `Phaser` variable. Do NOT include any `<script src=\"...\">` tags."
5. **Added static validation**: Regex check for `<script src="http` tags and network APIs
6. **Fixed fixtures**: Removed CDN script tags from all test fixtures

## Verification
After fix, all 20 tests pass with network blocking enabled. Generated artifacts:
- Load without console errors
- Render canvas content
- Respond to input
- Pass LLM review (9/10 score)
- Zero external network requests in browser devtools

## Lesson
**Any allowlist in a validation harness is a lie about the deployment environment.** If the target environment blocks external network, the validation must also block it completely.