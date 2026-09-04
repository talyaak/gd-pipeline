import http.server
import socket
import socketserver
import threading
import time
import asyncio
from pathlib import Path

from playwright.sync_api import sync_playwright
import os

from pipeline.schemas import ExecutionReport

# Path to vendored Phaser
VENDOR_DIR = Path(__file__).parent / "vendor"
CUSTOM_PHASER = VENDOR_DIR / "phaser.custom.min.js"
FULL_PHASER = VENDOR_DIR / "phaser.min.js"
MRAID_JS = VENDOR_DIR / "mraid.js"
PARTICLE_JS = VENDOR_DIR / "particle.js"
UI_JS = VENDOR_DIR / "ui.js"
ART_JS = VENDOR_DIR / "art.js"
JUICE_JS = VENDOR_DIR / "juice.js"

# Use custom build if available, fallback to full build
if CUSTOM_PHASER.exists():
    PHASER_JS = CUSTOM_PHASER.read_text(encoding="utf-8")
    print(f"[execute] Using custom Phaser build ({CUSTOM_PHASER.stat().st_size / 1024:.1f} KB)")
else:
    PHASER_JS = FULL_PHASER.read_text(encoding="utf-8")
    print(f"[execute] Using full Phaser build ({FULL_PHASER.stat().st_size / 1024:.1f} KB)")

# Read MRAID wrapper
MRAID_WRAPPER = MRAID_JS.read_text(encoding="utf-8") if MRAID_JS.exists() else ""
# Read particle.js
PARTICLE_JS_CONTENT = PARTICLE_JS.read_text(encoding="utf-8") if PARTICLE_JS.exists() else ""
# Read ui.js
UI_JS_CONTENT = UI_JS.read_text(encoding="utf-8") if UI_JS.exists() else ""
# Read art.js
ART_JS_CONTENT = ART_JS.read_text(encoding="utf-8") if ART_JS.exists() else ""
# Read juice.js
JUICE_JS_CONTENT = JUICE_JS.read_text(encoding="utf-8") if JUICE_JS.exists() else ""

INPUT_WAIT_MS = 500
POST_INPUT_WAIT_MS = 1500
LOAD_WAIT_MS = 2000
OBSERVATION_PERIOD_MS = 20000  # 20 seconds observation after inputs
OBSERVATION_INTERVAL_MS = 500   # Check every 500ms during observation


def _serve_dir(directory: Path):
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(directory), **kw)
    httpd = socketserver.TCPServer((("127.0.0.1", 0)), handler)
    httpd.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, port


def _has_vendor_scripts(html: str) -> bool:
    """Check if HTML already contains bundled vendor scripts (Phaser/Juice).
    Self-contained harness games include Phaser + Juice + game code in one <script> block.
    Heuristics: look for actual bundled code exports/definitions, not mere references.
    """
    import re
    script_blocks = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    if not script_blocks:
        return False
    combined_script = "\n".join(script_blocks)

    # Remove single-line comments (// ...) but NOT inside string literals.
    # Use a state machine approach: track whether we're inside a string.
    def strip_single_line_comments(js: str) -> str:
        result = []
        i = 0
        in_string = False
        string_char = ''
        while i < len(js):
            ch = js[i]
            if not in_string:
                if ch == '"' or ch == "'" or ch == '`':
                    in_string = True
                    string_char = ch
                    result.append(ch)
                elif ch == '/' and i + 1 < len(js) and js[i + 1] == '/':
                    # Skip to end of line
                    while i < len(js) and js[i] != '\n':
                        i += 1
                    if i < len(js):
                        result.append(js[i])  # keep the newline
                else:
                    result.append(ch)
            else:
                result.append(ch)
                if ch == '\\' and i + 1 < len(js):
                    result.append(js[i + 1])
                    i += 1
                elif ch == string_char:
                    in_string = False
            i += 1
        return ''.join(result)

    combined_script = strip_single_line_comments(combined_script)
    # Remove multi-line comments (/* ... */) - these don't appear in strings in our codebase
    combined_script = re.sub(r'/\*.*?\*/', '', combined_script, flags=re.DOTALL)

    # Harness games bundle the full Juice toolkit which exports: window.Juice = { ... }
    # They also define Juice classes like ScreenShake in the global scope.
    # The Phaser minified bundle is ~1MB and starts with a UMD wrapper.
    # Fixtures only REFERENCE Phaser/Juice without including them.
    markers = (
        "window.Juice = {",    # Actual Juice namespace export
        "class ScreenShake",   # Juice class definition (bundled)
        "window.__GAME__ = this.game",  # Harness-specific pattern
    )
    # Count how many markers appear in the cleaned script content
    match_count = sum(1 for marker in markers if marker in combined_script)
    return match_count >= 2


def run_execution_report(html: str, out_dir: Path) -> ExecutionReport:
    out_dir.mkdir(parents=True, exist_ok=True)

    # Skip vendor injection for self-contained HTML (harness games)
    needs_vendor = not _has_vendor_scripts(html)

    # Inject vendored Phaser into the HTML before serving
    # Insert before </head> or at the start of <body> if no </head>
    if needs_vendor:
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
        # Inject particle.js if available
        if PARTICLE_JS_CONTENT:
            if "</head>" in html:
                html = html.replace("</head>", f"<script>{PARTICLE_JS_CONTENT}</script></head>")
            else:
                html = html.replace("<body>", f"<body><script>{PARTICLE_JS_CONTENT}</script>")
        # Inject ui.js if available
        if UI_JS_CONTENT:
            if "</head>" in html:
                html = html.replace("</head>", f"<script>{UI_JS_CONTENT}</script></head>")
            else:
                html = html.replace("<body>", f"<body><script>{UI_JS_CONTENT}</script>")
        # Inject art.js if available
        if ART_JS_CONTENT:
            if "</head>" in html:
                html = html.replace("</head>", f"<script>{ART_JS_CONTENT}</script></head>")
            else:
                html = html.replace("<body>", f"<body><script>{ART_JS_CONTENT}</script>")
        # Inject juice.js if available
        if JUICE_JS_CONTENT:
            if "</head>" in html:
                html = html.replace("</head>", f"<script>{JUICE_JS_CONTENT}</script></head>")
            else:
                html = html.replace("<body>", f"<body><script>{JUICE_JS_CONTENT}</script>")

    game_path = out_dir / "game.html"
    game_path.write_text(html, encoding="utf-8")

    httpd, port = _serve_dir(out_dir)
    
    # Wait for server to be ready with a simple health check
    import urllib.request
    import urllib.error
    server_ready = False
    for _ in range(10):  # Up to ~1 second
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/game.html", timeout=0.5)
            server_ready = True
            break
        except Exception:
            time.sleep(0.1)
    
    if not server_ready:
        httpd.shutdown()
        return ExecutionReport(
            loaded=False,
            console_errors=["HTTP server failed to start"],
            canvas_rendered=False,
            input_response_detected=False,
            screenshot_before_path=str(out_dir / "verify_before.png"),
            screenshot_after_path=str(out_dir / "verify_after.png"),
            duration_ms=0,
            time_to_first_interaction_ms=None,
            engagement_duration_ms=None,
            completion_rate=0.0,
            final_html=html,
        )
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            context = browser.new_context()
            # Block ALL external network requests - no CDN allowlist
            context.route("**/*", lambda route: route.abort()
                           if route.request.url.startswith("http") and "127.0.0.1" not in route.request.url
                           else route.continue_())
            page = context.new_page()

            # Track time-to-first-interaction
            page.add_init_script("""
                window.__tti_start = performance.now();
                window.__tti_recorded = null;
                function recordTTI() {
                    if (window.__tti_recorded === null) {
                        window.__tti_recorded = performance.now() - window.__tti_start;
                    }
                }
                // Track meaningful interactions: pointerdown (click/tap), keyup (keyboard)
                document.addEventListener('pointerdown', recordTTI, { once: true, capture: true });
                document.addEventListener('keyup', recordTTI, { once: true, capture: true });
            """)

            console_errors: list[str] = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: console_errors.append(str(exc)))

            loaded = True
            try:
                placement_type = os.environ.get('PLACEMENT_TYPE', 'interstitial')
                url = f"http://127.0.0.1:{port}/game.html"
                if placement_type:
                    url += f"?placement={placement_type}"
                page.goto(url, timeout=15000)
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

            # bounding_box() is in page/viewport coordinates, not canvas-relative —
            # a canvas centered via CSS (as many generated games are) sits well away
            # from (0, 0), so every coordinate below must be offset by box["x"]/["y"].
            # Clicking box["width"]/2 directly (the previous behavior) missed the
            # canvas entirely on any non-flush-to-origin layout.
            origin_x = box["x"] if box else 0
            origin_y = box["y"] if box else 0
            w = box["width"] if box else 400
            h = box["height"] if box else 300
            cx = origin_x + w / 2
            cy = origin_y + h / 2

            page.keyboard.press("Space")
            page.wait_for_timeout(INPUT_WAIT_MS)
            page.mouse.click(cx, cy)
            page.wait_for_timeout(INPUT_WAIT_MS)
            page.mouse.click(origin_x + w * 0.35, origin_y + h * 0.5)
            page.wait_for_timeout(150)
            page.mouse.click(origin_x + w * 0.55, origin_y + h * 0.5)
            page.wait_for_timeout(INPUT_WAIT_MS)

            drag_start_x = origin_x + w * 0.3
            drag_end_x = origin_x + w * 0.7
            page.mouse.move(drag_start_x, cy)
            page.mouse.down()
            for step in range(1, 6):
                page.mouse.move(drag_start_x + (drag_end_x - drag_start_x) * step / 5, cy)
                page.wait_for_timeout(30)
            page.mouse.up()
            page.wait_for_timeout(POST_INPUT_WAIT_MS)

            # Extended observation period to measure engagement and completion
            engagement_start_time = None
            engagement_end_time = None
            total_engagement_ms = 0
            completion_detected = False
            win_state_detected = False

            # Observe for extended period to measure engagement
            observation_end = time.time() + (OBSERVATION_PERIOD_MS / 1000)
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
                                // Map common scene names to states (substring match for flexibility)
                                const sceneNames = activeScenes.map(s => s.settings.key.toLowerCase());
                                if (sceneNames.some(name => name.includes('play') || name.includes('game') || name.includes('level'))) {
                                    return { state: 'playing', reason: 'phaser scene' };
                                }
                                if (sceneNames.some(name => name.includes('menu') || name.includes('main') || name.includes('start'))) {
                                    return { state: 'menu', reason: 'phaser scene' };
                                }
                                if (sceneNames.some(name => name.includes('gameover') || name.includes('over'))) {
                                    return { state: 'gameover', reason: 'phaser scene' };
                                }
                                if (sceneNames.some(name => name.includes('win') || name.includes('won') || name.includes('victory') || name.includes('success'))) {
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

                        // Check for session time increasing as a sign of active play
                        if (game.sessionTime !== undefined && game.sessionTime > 0) {
                            return { state: 'playing', reason: 'sessionTime > 0' };
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
                        completion_detected = True
                    elif current_state in ['gameover', 'game over', 'over'] and engagement_start_time is not None:
                        # Game over after having played = completed a session
                        completion_detected = True

                except Exception as e:
                    # If we can't read game state, assume we're still engaged if we were before
                    pass
                
                page.wait_for_timeout(OBSERVATION_INTERVAL_MS)

            # If we started engagement but never ended it, set end time to now
            if engagement_start_time is not None and engagement_end_time is None:
                engagement_end_time = time.time()

            # Calculate total engagement time
            if engagement_start_time is not None and engagement_end_time is not None:
                total_engagement_ms = int((engagement_end_time - engagement_start_time) * 1000)

            # For completion rate, if we detected a win state, it's 1.0
            # If we detected game over after playing, it's also 1.0 (completed a session)
            # Otherwise, we could calculate based on engagement time vs expected session time
            completion_rate = None
            if win_state_detected:
                completion_rate = 1.0
            elif completion_detected:
                completion_rate = 1.0
            else:
                # Fallback: calculate based on engagement time vs reasonable session time
                # Use target session seconds from typical range (30s) as baseline
                target_session_ms = 30 * 1000  # 30 seconds
                if total_engagement_ms > 0:
                    completion_rate = min(total_engagement_ms / target_session_ms, 1.0)
                else:
                    completion_rate = 0.0

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
                    # Check scene is active and indicates gameplay - robust logic with fallbacks
                    scene_active_and_gameplay = page.evaluate("""() => {
                        const game = window.__GAME__;
                        if (!game) return false;

                        // Check for game.state property - if 'playing', we're good
                        if (game.state === 'playing') {
                            return true;
                        }

                        // Check for scene-based states as fallback (even if game.state exists but isn't 'playing')
                        if (game.scene && game.scene.scenes) {
                            const activeScenes = game.scene.scenes.filter(s => s.visible && s.active);
                            if (activeScenes.length > 0) {
                                const sceneName = activeScenes[0].settings.key.toLowerCase();
                                if (sceneName.includes('game') || sceneName.includes('play')) {
                                    return true;
                                }
                            }
                        }

                        // Check for score increasing as a sign of active play
                        if (game.registry && typeof game.registry.get === 'function') {
                            try {
                                const score = game.registry.get('score');
                                if (typeof score === 'number' && score > 0) {
                                    return true; // score > 0 indicates gameplay
                                }
                            } catch(e) {/* ignore */}
                        }

                        // Check for session time increasing as a sign of active play
                        if (game.sessionTime !== undefined && game.sessionTime > 0) {
                            return true; // sessionTime > 0 indicates gameplay
                        }

                        // Default to false if we can't determine
                        return false;
                    }""")
                    if not scene_active_and_gameplay:
                        console_errors.append("Semantic validation: no active gameplay scene")
                        semantic_ok = False
                    else:
                        # Check score registry
                        has_score = page.evaluate("() => window.__GAME__.registry.has('score')")
                        if has_score:
                            score_val = page.evaluate("() => window.__GAME__.registry.get('score')")
                            if not isinstance(score_val, (int, float)) or score_val < 0:
                                console_errors.append("Semantic validation: invalid score value")
                                semantic_ok = False

                        # Check not game over immediately — but a game that's over
                        # *after* real engagement is a working win/lose condition,
                        # not a bug. The observation loop above already tracked
                        # exactly this distinction (engagement_start_time is only
                        # set once genuine play was observed); reuse it instead of
                        # re-deriving a verdict from a single end-of-test snapshot
                        # that can't tell "died instantly" from "played a full
                        # session and correctly ended" apart on its own.
                        game_over = page.evaluate("() => window.__GAME__.registry.get('gameOver') === true")
                        if game_over and engagement_start_time is None:
                            console_errors.append("Semantic validation: game over immediately")
                            semantic_ok = False
            except Exception as exc:
                console_errors.append(f"Semantic validation error: {exc}")
                semantic_ok = False

            duration_ms = LOAD_WAIT_MS + 3 * INPUT_WAIT_MS + POST_INPUT_WAIT_MS + POST_INPUT_WAIT_MS + OBSERVATION_PERIOD_MS

            # Measure time-to-first-interaction
            time_to_first_interaction_ms = None
            try:
                tti = page.evaluate("() => window.__tti_recorded")
                if tti is not None:
                    time_to_first_interaction_ms = int(tti)
            except Exception:
                pass

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
        time_to_first_interaction_ms=time_to_first_interaction_ms,
        engagement_duration_ms=total_engagement_ms if total_engagement_ms > 0 else None,
        completion_rate=completion_rate,
        final_html=html,
    )


async def async_run_execution_report(html: str, out_dir: Path) -> ExecutionReport:
    """Async wrapper for run_execution_report to enable parallel execution.
    
    Runs the synchronous run_execution_report in a thread pool executor
    to allow multiple browser instances to run concurrently.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, run_execution_report, html, out_dir)