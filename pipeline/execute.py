import http.server
import socketserver
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

from pipeline.schemas import ExecutionReport

# Path to vendored Phaser
VENDOR_DIR = Path(__file__).parent / "vendor"
PHASER_JS = (VENDOR_DIR / "phaser.min.js").read_text(encoding="utf-8")

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
