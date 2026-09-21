# Phaser Vendoring for Self-Contained Playables

## Version Selection
- **Phaser 3.80.1** — Current stable, ~1.18MB minified
- Source: `https://cdn.jsdelivr.net/npm/phaser@3.80.1/dist/phaser.min.js`
- Verify: `curl -sL <url> -o phaser.min.js && wc -c phaser.min.js`

## Size Optimization Options
| Approach | Size | Trade-off |
|----------|------|-----------|
| Full Phaser 3.80.1 | 1.18MB | Full API, all features |
| Phaser 3 custom build | ~400KB | Requires build step, only needed modules |
| Minimal runtime (vanilla JS) | ~15KB | No Phaser API, rewrite codegen prompt |

## Injection Pattern
```python
# In execute.py
VENDOR_DIR = Path(__file__).parent / "vendor"
PHASER_JS = (VENDOR_DIR / "phaser.min.js").read_text(encoding="utf-8")

def run_execution_report(html: str, out_dir: Path) -> ExecutionReport:
    if "</head>" in html:
        html = html.replace("</head>", f"<script>{PHASER_JS}</script></head>")
    else:
        html = html.replace("<body>", f"<body><script>{PHASER_JS}</script>")
    # ... serve and validate
```

## Distribution
For standalone artifacts (not served by harness), create inlined version:
```bash
cat generated_game.html | sed '/<\/head>/i\\<script>$(cat pipeline/vendor/phaser.min.js)<\/script>' > generated_game_standalone.html
```