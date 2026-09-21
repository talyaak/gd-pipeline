# Injection Pattern Reference

## Core Injection Function

```python
from pathlib import Path

VENDOR_DIR = Path(__file__).parent / "vendor"
PHASER_JS = (VENDOR_DIR / "phaser.min.js").read_text(encoding="utf-8")

def inject_vendored_phaser(html: str) -> str:
    """Inject vendored Phaser into HTML before serving for validation."""
    if "</head>" in html:
        return html.replace("</head>", f"<script>{PHASER_JS}</script></head>")
    else:
        return html.replace("<body>", f"<body><script>{PHASER_JS}</script>")
```

## Usage in Execution Harness

```python
def run_execution_report(html: str, out_dir: Path) -> ExecutionReport:
    # Inject BEFORE writing to disk and serving
    html = inject_vendored_phaser(html)
    
    game_path = out_dir / "game.html"
    game_path.write_text(html, encoding="utf-8")
    
    # ... serve and test with Playwright
```

## Key Points

1. **Inject at validation time, not generation time** — The LLM-generated code should never contain `<script src="...">` tags for Phaser
2. **String replacement is simple and reliable** — No template engine needed
3. **Handle both `</head>` and `<body>`** — Some generators omit `<head>`
4. **Read vendor file once at module load** — Not per-request