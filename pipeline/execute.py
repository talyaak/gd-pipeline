import http.server
import socketserver
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

from pipeline.schemas import ExecutionReport

# Path to vendored Phaser
VENDOR_DIR = Path(__file__).parent / "vendor"
CUSTOM_PHASER = VENDOR_DIR / "phaser.custom.min.js"
FULL_PHASER = VENDOR_DIR / "phaser.min.js"
MRAID_JS = VENDOR_DIR / "mraid.js"

# Use custom build if available, fallback to full build
if CUSTOM_PHASER.exists():
    PHASER_JS = CUSTOM_PHASER.read_text(encoding="utf-8")
    print(f"[execute] Using custom Phaser build ({CUSTOM_PHASER.stat().st_size / 1024:.1f} KB)")
else:
    PHASER_JS = FULL_PHASER.read_text(encoding="utf-8")
    print(f"[execute] Using full Phaser build ({FULL_PHASER.stat().st_size / 1024:.1f} KB)")

# Read MRAID wrapper
MRAID_WRAPPER = MRAID_JS.read_text(encoding="utf-8") if MRAID_JS.exists() else ""

INPUT_WAIT_MS = 500
POST_INPUT_WAIT_MS = 1500
LOAD_WAIT_MS = 2000


def _serve_dir(directory: Path):
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(directory), **kw)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, port


def run_execution_report(html: str, out_dir: Path) -> ExecutionReport:
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Inject vendored Phaser into the HTML before serving
    # Insert before </head> or at the start of <body> if no </head>
    if "</head>" in html:
        html = html.replace("</head>", f"<script>{PHASER_JS}</script></head>")
    else:
        html = html.replace("<body>", f"<body><script>{PHASER_JS}</script>")
    
    # Inject MRAID wrapper if available
    if MRAID_WRAPPER:
        if "</head>" in html:
            html = html.replace("</head>", f"<script>{MRAID_WRAPPER}</script></head>")
        else:
            html = html.replace("<body>", f"<body><script>{MRAID_WRAPPER}</script>")
    
    game_path = out_dir / "game.html"
    game_path.write_text(html, encoding="utf-8")

    httpd, port = _serve_dir(out_dir)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            context = browser.new_context()
            # Block ALL external network requests - no CDN allowlist
            context.route("**/*", lambda route: route.abort()
                           if route.request.url.startswith("http") and "127.0.0.1" not in route.request.url
                           else route.continue_())
            page = context.new_page()

            console_errors: list[str] = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: console_errors.append(str(exc)))

            loaded = True
            try:
                page.goto(f"http://127.0.0.1:{port}/game.html", timeout=15000)
            except Exception as exc:
                loaded = False
                console_errors.append(f"navigation failed: {exc}")

            page.wait_for_timeout(LOAD_WAIT_MS)

            canvas = page.query_selector("canvas")
            box = canvas.bounding_box() if canvas else None
            canvas_rendered = bool(box and box["width"] > 0 and box["height"] > 0)

            before_path = out_dir / "verify_before.png"
            page.screenshot(path=str(before_path))
            before_bytes = before_path.read_bytes()

            page.keyboard.press("Space")
            page.wait_for_timeout(INPUT_WAIT_MS)
            page.mouse.click(box["width"] / 2 if box else 200, box["height"] / 2 if box else 150)
            page.wait_for_timeout(POST_INPUT_WAIT_MS)

            after_path = out_dir / "verify_after.png"
            page.screenshot(path=str(after_path))
            after_bytes = after_path.read_bytes()

            input_response_detected = before_bytes != after_bytes

            # Semantic validation: check window.__GAME__ exposure and game state
            semantic_ok = True
            try:
                game_exposed = page.evaluate("() => typeof window.__GAME__ !== 'undefined'")
                if not game_exposed:
                    console_errors.append("Semantic validation: window.__GAME__ not exposed")
                    semantic_ok = False
                else:
                    # Check scene is active
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
                    
                    # Check not game over immediately
                    game_over = page.evaluate("() => window.__GAME__.registry.get('gameOver') === true")
                    if game_over:
                        console_errors.append("Semantic validation: game over immediately")
                        semantic_ok = False
                    
                    # MRAID validation
                    mraid_ok = True
                    try:
                        mraid_exists = page.evaluate("() => typeof mraid !== 'undefined'")
                        if not mraid_exists:
                            console_errors.append("MRAID validation: mraid not exposed")
                            mraid_ok = False
                        else:
                            # Check mraid.getVersion()
                            version = page.evaluate("() => mraid.getVersion()")
                            if version != "3.0":
                                console_errors.append(f"MRAID validation: version {version}, expected 3.0")
                                mraid_ok = False
                            
                            # Check mraid.getState()
                            state = page.evaluate("() => mraid.getState()")
                            if state != "default" and state != "loading" and state != "ready":
                                console_errors.append(f"MRAID validation: unexpected state {state}")
                                mraid_ok = False
                            
                            # Check mraid.open exists
                            has_open = page.evaluate("() => typeof mraid.open === 'function'")
                            if not has_open:
                                console_errors.append("MRAID validation: mraid.open not available")
                                mraid_ok = False
                            
                            # Check CTA button exists and has handler
                            has_cta = page.evaluate("() => window.__GAME__ && window.__GAME__.scene && window.__GAME__.scene.scenes.some(s => s.ctaButton)")
                            if not has_cta:
                                console_errors.append("MRAID validation: CTA button not found on scene")
                                mraid_ok = False
                    except Exception as exc:
                        console_errors.append(f"MRAID validation error: {exc}")
                        mraid_ok = False
                    
                    if not mraid_ok:
                        semantic_ok = False
                        
            except Exception as exc:
                console_errors.append(f"Semantic validation error: {exc}")
                semantic_ok = False

            duration_ms = LOAD_WAIT_MS + INPUT_WAIT_MS + POST_INPUT_WAIT_MS

            browser.close()
    finally:
        httpd.shutdown()

    return ExecutionReport(
        loaded=loaded,
        console_errors=console_errors,
        canvas_rendered=canvas_rendered,
        input_response_detected=input_response_detected,
        screenshot_before_path=str(before_path),
        screenshot_after_path=str(after_path),
        duration_ms=duration_ms,
    )
