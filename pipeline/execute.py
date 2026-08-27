import http.server
import socketserver
import threading
import time
import asyncio
from pathlib import Path

from playwright.sync_api import sync_playwright

from pipeline.schemas import ExecutionReport

# Path to vendored Phaser
VENDOR_DIR = Path(__file__).parent / "vendor"
CUSTOM_PHASER = VENDOR_DIR / "phaser.custom.min.js"
FULL_PHASER = VENDOR_DIR / "phaser.min.js"
MRAID_JS = VENDOR_DIR / "mraid.js"
PARTICLE_JS = VENDOR_DIR / "particle.js"
UI_JS = VENDOR_DIR / "ui.js"
ART_JS = VENDOR_DIR / "art.js"

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

INPUT_WAIT_MS = 500
POST_INPUT_WAIT_MS = 1500
LOAD_WAIT_MS = 2000
OBSERVATION_PERIOD_MS = 20000  # 20 seconds observation after inputs
OBSERVATION_INTERVAL_MS = 500   # Check every 500ms during observation


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
                    # Check scene is active
                    scene_active = page.evaluate("() => window.__GAME__.scene.isActive('Play') || window.__GAME__.scene.isActive('GameScene') || window.__GAME__.scene.isActive('MainScene') || window.__GAME__.scene.isActive('PlayScene')")
                    if not scene_active:
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
                            if version not in ["2.0", "3.0"]:
                                console_errors.append(f"MRAID validation: version {version}, expected 2.0 or 3.0")
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