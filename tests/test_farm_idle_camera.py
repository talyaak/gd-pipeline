"""
Camera/world-scroll mechanics tests for farm_idle: split out of the former
monolithic tests/test_farm_idle_real_device.py (Instinct Wire issue #2).

Covers the scrolling-world camera introduced for the collectible/producer
world -- world bounds, natural follow/clamping, one-time boot framing,
smooth (non-snapping) deadzone lerp, input tracking under an active pan,
and the world-camera-to-UI-camera coordinate conversion used by
_flyCoinsToCounter for the composited HUD coin-flight effect.
"""
import pytest
from playwright.sync_api import sync_playwright
from farm_idle_test_support import _boot, SHORT_VIEWPORTS, TALL_VIEWPORT, _read_pixel_region_via_screenshot


def test_camera_bounds_are_fixed_world_size_independent_of_viewport():
    """Section D: camera world bounds must be the fixed WORLD_W x WORLD_H
    (1440x2000) at every viewport, never derived from the viewport itself --
    proves the bounds stopped being viewport-height-derived."""
    for viewport_width, viewport_height, viewport_name in [
        (390, 650, "iPhone_effective_short"),
        (390, 844, "iPhone_12_tall_contrast"),
    ]:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=['--no-sandbox'])
            page = browser.new_page(
                viewport={'width': viewport_width, 'height': viewport_height},
                has_touch=True, is_mobile=True
            )
            _boot(page, viewport_name)

            bounds = page.evaluate("""(() => {
                const scene = window.__GAME__.scene.scenes[0];
                const b = scene.cameras.main.getBounds();
                return { width: b.width, height: b.height };
            })""")

            browser.close()

            assert bounds['width'] == 1440, (
                f"[{viewport_name}] camera bounds width {bounds['width']} != 1440 "
                f"(WORLD_W) -- bounds must be fixed, not viewport-derived"
            )
            assert bounds['height'] == 2000, (
                f"[{viewport_name}] camera bounds height {bounds['height']} != 2000 "
                f"(WORLD_H) -- bounds must be fixed, not viewport-derived"
            )



def test_coin_flight_starts_at_visible_source_under_world_scroll():
    """Behavioral/pixel proof (per Instinct gate review on the two-camera
    split) that _flyCoinsToCounter's world-to-HUD coordinate conversion is
    correct: a coin's FIRST rendered pixel must be at the farmer's actual
    on-screen position, not at some offset, once the world camera has
    scrolled both horizontally and vertically away from its boot position.
    Object-coordinate assertions (checking .x/.y properties) would pass
    even with the exact bug this catches -- only a real rendered pixel,
    at the real physical position a player would see, proves the fix.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True
        )
        _boot(page, "iPhone_12_tall_contrast")

        # Force nonzero horizontal AND vertical world scroll (real frames,
        # not scene.update() -- camera follow easing runs on Phaser's own
        # render loop).
        page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            scene.farmer.x = 1100;
            scene.farmer.y = 1700;
        }""")
        page.wait_for_timeout(600)

        setup = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            const cam = scene.cameras.main;
            const zoom = cam.zoom;
            // Farmer's actual physical (screen) position -- what a player
            // sees. Phaser cameras default to a CENTERED origin (0.5, 0.5),
            // and the world camera (unlike uiCamera) is never centerOn'd --
            // it just follows the farmer -- so plain (worldX - scrollX)*zoom
            // is NOT the true screen position; the origin term must be
            // included (verified against camera.getWorldPoint-sampled
            // ground truth).
            const farmerScreenX = (scene.farmer.x - cam.scrollX) * zoom +
                cam.originX * cam.width * (1 - zoom);
            const farmerScreenY = (scene.farmer.y - cam.scrollY) * zoom +
                cam.originY * cam.height * (1 - zoom);
            // Trigger exactly one coin, sourced at the farmer's current
            // world position -- same call shape _sellAtStall() uses.
            scene._flyCoinsToCounter(1, scene.farmer.x, scene.farmer.y);
            // Freeze the scatter-burst tween immediately, in this same
            // synchronous turn, before any time has elapsed. page.evaluate()
            // and page.screenshot() are separate round-trips (unlike this
            // single synchronous call), so without pausing, real wall-clock
            // time could elapse before the screenshot is taken and the
            // 150ms tween would have already moved the coin measurably away
            // from its start position -- this decouples the pixel assertion
            // from that round-trip timing entirely.
            scene.tweens.pauseAll();
            return {
                farmerScreenX, farmerScreenY,
                worldScrollX: cam.scrollX, worldScrollY: cam.scrollY,
            };
        }""")

        assert setup["worldScrollX"] > 50 and setup["worldScrollY"] > 50, (
            f"world camera didn't scroll enough to be a meaningful proof: "
            f"scrollX={setup['worldScrollX']}, scrollY={setup['worldScrollY']}"
        )

        # No wait: read the very next composited frame, before the coin's
        # scatter-burst tween (150ms) has had time to move it away from its
        # start position.
        region_size = 24
        rows = _read_pixel_region_via_screenshot(
            page,
            round(setup["farmerScreenX"] - region_size / 2),
            round(setup["farmerScreenY"] - region_size / 2),
            region_size, region_size,
        )
        browser.close()

        pixels = [p for row in rows for p in row]
        has_gold_pixel = any(r > 200 and 150 < g < 230 and b < 60 for r, g, b in pixels)

        assert has_gold_pixel, (
            f"no gold (0xffd700-ish) coin pixel found in a {region_size}x{region_size}px "
            f"region centered on the farmer's actual screen position "
            f"({setup['farmerScreenX']:.1f}, {setup['farmerScreenY']:.1f}) after world scroll "
            f"({setup['worldScrollX']:.1f}, {setup['worldScrollY']:.1f}) -- the coin rendered "
            f"somewhere else, meaning the world-to-HUD conversion is wrong"
        )



@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", SHORT_VIEWPORTS + [TALL_VIEWPORT])
def test_farmer_clamps_at_full_world_bounds(viewport_width, viewport_height, viewport_name):
    """Section D sub-dispatch 3 required proof: the farmer's movement clamp
    widened from viewport-relative bounds to the full fixed world bounds
    (WORLD_W x WORLD_H). Driven through the REAL on-screen joystick input
    path -- actual held pointer down/move/up at real screen coordinates,
    exercising this.input's pointerdown/pointermove/pointerup listeners,
    _activateJoystick/_updateJoystick, and _moveFarmerByJoystick's own
    per-frame clamp exactly as a real player's drag would -- not a direct
    call to _moveFarmerByJoystick with a hand-set joystickVector. Only the
    STARTING farmer position (arrange step, not the thing under test) is set
    directly; the movement and clamp are driven entirely through touch.

    Assert clamps to exactly FARMER_RADIUS / WORLD_W - FARMER_RADIUS /
    PLOT_AREA_TOP + FARMER_RADIUS / WORLD_H - FARMER_RADIUS -- not the old
    viewport-relative bounds (LOGICAL_W / layout.visibleWorldHeight), which
    would be smaller than the real world bounds at every one of these
    viewports.
    """
    FARMER_RADIUS = 32
    WORLD_W = 1440
    WORLD_H = 2000
    PLOT_AREA_TOP = 192

    # (start world position near the edge, drag direction in screen space,
    # axis being clamped, expected clamped value)
    # Drag delta: must clear the joystick's full-magnitude threshold
    # (JOYSTICK_RADIUS=80 logical * worldZoom, i.e. ~40-46px screen at
    # these 4 viewports). 50px clears that with margin. Reduced from an
    # original 150px, which could push the drag target off-screen from
    # the (*, 0.15)/(0.15, *) fallback candidates at some viewport sizes
    # -- investigated as a candidate explanation for an intermittent CI
    # (and, on retry, occasionally local) failure at the "top" case, but
    # the actual cause turned out to be a separate race (see the settle
    # wait added after mouse.down() below) -- keeping this reduction
    # anyway since it removes a real, if apparently harmless in practice,
    # off-screen-target risk.
    DRAG = 50
    cases = [
        ((WORLD_W - 200, 1000), (DRAG, 0), "x", WORLD_W - FARMER_RADIUS, "right"),
        ((200, 1000), (-DRAG, 0), "x", FARMER_RADIUS, "left"),
        ((700, WORLD_H - 200), (0, DRAG), "y", WORLD_H - FARMER_RADIUS, "bottom"),
        ((700, PLOT_AREA_TOP + 200), (0, -DRAG), "y", PLOT_AREA_TOP + FARMER_RADIUS, "top"),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": viewport_width, "height": viewport_height}, has_touch=True, is_mobile=True
        )
        _boot(page, viewport_name)

        # Candidate touch-start points to try, in order -- the camera's
        # visible world span can be tall enough at some edge/viewport
        # combos to put the (world-fixed) upgrade pad under screen center,
        # which would swallow the pointerdown as a pad tap instead of
        # activating the joystick (see _activateJoystick's hitTestPointer
        # guard). Falling back to alternates keeps the test testing the
        # clamp, not "which exact pixel is safe this viewport."
        candidates = [
            (viewport_width * 0.5, viewport_height * 0.5),
            (viewport_width * 0.5, viewport_height * 0.15),
            (viewport_width * 0.15, viewport_height * 0.5),
        ]

        for (start_x, start_y), (ddx, ddy), axis, expected, label in cases:
            page.evaluate(
                """([x, y]) => {
                    const scene = window.__GAME__.scene.scenes[0];
                    scene.farmer.x = x;
                    scene.farmer.y = y;
                }""",
                [start_x, start_y],
            )
            page.wait_for_timeout(50)  # let the camera settle near the new start position

            # Real held touch/pointer drag: down at a safe screen point,
            # move outward past JOYSTICK_RADIUS in the target direction
            # (150px screen delta always exceeds the ~40-46px needed at
            # these viewports' worldZoom), hold for real frames so
            # _moveFarmerByJoystick's per-frame clamp actually runs and
            # settles, then release.
            active = False
            for cx, cy in candidates:
                page.mouse.move(cx, cy)
                page.mouse.down()
                # Small settle wait: checking joystickActive immediately
                # after mouse.down() can occasionally race the browser's
                # own event dispatch (rare, intermittent -- caught via
                # repeated local + CI runs, not reproducible on demand).
                # This closes that race without slowing the common case
                # much.
                page.wait_for_timeout(50)
                active = page.evaluate("() => window.__GAME__.scene.scenes[0].joystickActive")
                if active:
                    break
                page.mouse.up()
            assert active, (
                f"{viewport_name} ({label}): joystick did not activate at any candidate screen "
                f"point {candidates} -- all landed on an interactive element"
            )
            page.mouse.move(cx + ddx, cy + ddy, steps=5)

            # Poll for the clamp to actually settle instead of one fixed
            # wait -- CI runners can be measurably slower than a local dev
            # machine (observed: a 2500ms fixed wait was enough locally,
            # multiple runs, but left the farmer short of the clamp on a
            # real CI run). Polling in 400ms increments up to 6s total
            # makes this robust to that variance either way.
            final = None
            for _ in range(15):
                page.wait_for_timeout(400)
                final = page.evaluate("() => ({ x: window.__GAME__.scene.scenes[0].farmer.x, y: window.__GAME__.scene.scenes[0].farmer.y })")
                if final[axis] == expected:
                    break
            page.mouse.up()
            page.wait_for_timeout(50)

            assert final[axis] == expected, (
                f"{viewport_name} ({label}): real joystick drag clamped farmer.{axis} to "
                f"{final[axis]}, expected {expected}"
            )

        browser.close()



@pytest.mark.slow
def test_joystick_tracks_finger_direction_after_large_pan():
    """Section D acceptance criterion 11 (input under scroll), first half:
    with the world camera panned far from its boot position, a real held
    pointer drag must still produce a joystickVector whose sign/direction
    matches the actual screen-space drag, and a visible thumb offset in the
    same direction -- proving joystick input stays purely screen-space
    (only ever divided by worldZoom, per _activateJoystick/_updateJoystick)
    and is never contaminated by camera scroll.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        _boot(page, "iPhone_12_tall_contrast")

        page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            scene.farmer.x = 1200;
            scene.farmer.y = 1700;
        }""")
        page.wait_for_timeout(600)

        scroll = page.evaluate("() => { const c = window.__GAME__.scene.scenes[0].cameras.main; return { x: c.scrollX, y: c.scrollY }; }")
        assert scroll["x"] > 50 and scroll["y"] > 50, (
            f"world camera didn't pan enough to be a meaningful proof: {scroll}"
        )

        cx, cy = 195, 422  # roughly screen center at 390x844
        ddx, ddy = 60, -100  # drag right and up
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.wait_for_timeout(50)  # settle wait -- see other joystick tests for why
        active = page.evaluate("() => window.__GAME__.scene.scenes[0].joystickActive")
        assert active, "joystick did not activate on pointerdown at screen center"

        page.mouse.move(cx + ddx, cy + ddy, steps=5)
        state = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            return {
                vector: scene.joystickVector,
                center: scene.joystickCenter,
                thumbX: scene.joystickThumb ? scene.joystickThumb.x : null,
                thumbY: scene.joystickThumb ? scene.joystickThumb.y : null,
            };
        }""")
        page.mouse.up()
        browser.close()

        assert state["vector"]["x"] > 0 and state["vector"]["y"] < 0, (
            f"joystick vector direction doesn't match the drag (right+up expected, got "
            f"{state['vector']}) after a large camera pan"
        )
        assert (state["thumbX"] - state["center"]["x"]) > 0 and (state["thumbY"] - state["center"]["y"]) < 0, (
            f"joystick thumb visual offset doesn't match the drag direction: "
            f"thumb=({state['thumbX']}, {state['thumbY']}) center={state['center']}"
        )



@pytest.mark.slow
def test_pad_tap_after_scroll_does_not_spawn_joystick():
    """Section D acceptance criterion 11 (input under scroll), second half:
    a real tap on the in-world upgrade pad after the camera has scrolled
    must open the sheet WITHOUT also activating the floating joystick --
    the global pointerdown handler's hitTestPointer guard should return
    early on any interactive hit (the pad) before ever calling
    _activateJoystick, so a pad tap and a joystick spawn should never
    happen together.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        _boot(page, "iPhone_12_tall_contrast")

        page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            const pad = scene._computePadLayout();
            scene.farmer.x = pad.centerX + 120;
            scene.farmer.y = pad.centerY - 80;
        }""")
        page.wait_for_timeout(600)

        tap_point = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            const cam = scene.cameras.main;
            function worldToScreen(camera, wx, wy) {
                const p0 = camera.getWorldPoint(0, 0);
                const p1 = camera.getWorldPoint(100, 0);
                const p2 = camera.getWorldPoint(0, 100);
                const sx = (wx - p0.x) / (p1.x - p0.x) * 100;
                const sy = (wy - p0.y) / (p2.y - p0.y) * 100;
                return { x: sx, y: sy };
            }
            const pad = scene._computePadLayout();
            const screen = worldToScreen(cam, pad.centerX, pad.centerY);
            return {
                screenX: screen.x, screenY: screen.y,
                worldScrollX: cam.scrollX, worldScrollY: cam.scrollY,
            };
        }""")

        assert tap_point["worldScrollX"] > 50 and tap_point["worldScrollY"] > 50, (
            f"world camera didn't scroll enough to be a meaningful proof: {tap_point}"
        )

        page.touchscreen.tap(tap_point["screenX"], tap_point["screenY"])
        page.wait_for_timeout(150)

        after = page.evaluate("() => { const s = window.__GAME__.scene.scenes[0]; return { sheetVisible: s.sheetVisible, joystickActive: s.joystickActive }; }")
        browser.close()

        assert after["sheetVisible"], (
            f"pad tap after scroll did not open the sheet: {after}"
        )
        assert not after["joystickActive"], (
            f"pad tap after scroll incorrectly also activated the joystick: {after}"
        )



@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", SHORT_VIEWPORTS + [TALL_VIEWPORT])
def test_boot_camera_worldview_pinned(viewport_width, viewport_height, viewport_name):
    """Starting-hub framing (Section D acceptance round): pins the exact
    camera.worldView produced by the new explicit one-time _onResize
    framing step (this._hasFramedInitialView) at boot, at all 4 real-device
    viewports. This is the "before/after-identical" regression proof --
    the explicit step is an architectural change (making an already-correct
    accidental clamp result into a deliberate, named one), not a visual
    one, so this pins it to the exact same values measured before that
    change existed.
    """
    EXPECTED_WORLDVIEW = {
        "iPhone_effective_short": {"x": 0, "y": 0, "width": 720, "height": 1200},
        "iPhone_11_short_chrome": {"x": 0, "y": 0, "width": 720, "height": 1217.3913043478262},
        "Galaxy_short_chrome": {"x": 0, "y": 0, "width": 720, "height": 1230},
        "iPhone_12_tall_contrast": {"x": 0, "y": 0, "width": 720, "height": 1558.1538461538462},
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": viewport_width, "height": viewport_height}, has_touch=True, is_mobile=True
        )
        _boot(page, viewport_name)

        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            const cam = scene.cameras.main;
            return {
                worldView: { x: cam.worldView.x, y: cam.worldView.y, width: cam.worldView.width, height: cam.worldView.height },
                hasFramedFlag: scene._hasFramedInitialView,
            };
        }""")
        browser.close()

        assert result["hasFramedFlag"] is True, (
            f"{viewport_name}: the explicit one-time initial-framing step did not run "
            f"(_hasFramedInitialView is {result['hasFramedFlag']})"
        )
        expected = EXPECTED_WORLDVIEW[viewport_name]
        for key in ("x", "y", "width", "height"):
            assert abs(result["worldView"][key] - expected[key]) < 0.01, (
                f"{viewport_name}: boot worldView.{key} = {result['worldView'][key]}, "
                f"expected {expected[key]} (full worldView: {result['worldView']})"
            )



@pytest.mark.slow
def test_no_snap_on_first_input_after_boot():
    """Starting-hub framing, "no snap" requirement: when the player's first
    real input crosses the deadzone and the camera starts following for
    the first time, the camera position must change smoothly (per
    startFollow's lerp), not jump straight to the target in one frame.
    Proven by sampling camera.scroll at real 150ms intervals during a real
    held drag and confirming no single sample-to-sample step accounts for
    an outsized share of the total distance traveled -- a genuine snap
    would show almost the entire distance covered in one step; smooth
    lerp-based follow shows a gradual, accelerating pattern instead
    (verified empirically via a dry run before writing this test: deltas
    grew 0 -> 3.5 -> 10 -> 25 -> 78 while covering a total of ~384 units,
    no single step anywhere close to the total).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        _boot(page, "iPhone_12_tall_contrast")

        before = page.evaluate("() => { const c = window.__GAME__.scene.scenes[0].cameras.main; return { x: c.scrollX, y: c.scrollY }; }")

        cx, cy = 195, 700
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.mouse.move(cx + 100, cy, steps=3)  # full-magnitude rightward push

        samples = []
        for _ in range(20):
            page.wait_for_timeout(150)
            samples.append(page.evaluate("() => { const c = window.__GAME__.scene.scenes[0].cameras.main; return { x: c.scrollX, y: c.scrollY }; }"))
        page.mouse.up()
        browser.close()

        prev = before
        max_delta = 0
        for s in samples:
            d = ((s["x"] - prev["x"]) ** 2 + (s["y"] - prev["y"]) ** 2) ** 0.5
            max_delta = max(max_delta, d)
            prev = s
        total_distance = ((samples[-1]["x"] - before["x"]) ** 2 + (samples[-1]["y"] - before["y"]) ** 2) ** 0.5

        assert total_distance > 50, (
            f"camera didn't move enough during the held input to be a meaningful proof: "
            f"total_distance={total_distance}"
        )
        assert max_delta < total_distance * 0.5, (
            f"a single sample-to-sample step ({max_delta:.1f}) accounted for more than half "
            f"the total camera movement ({total_distance:.1f}) on the first real input after "
            f"boot -- looks like a snap, not a smooth follow"
        )


@pytest.mark.slow
def test_joystick_drag_through_upgrade_pad_keeps_moving_and_does_not_open_sheet():
    """Hotfix regression test (Instinct Wire issue #2, priority interrupt
    5725435315): a joystick drag that crosses the upgrade pad's hit area must
    keep moving the farmer the whole time, releasing over the pad afterward
    must NOT open the upgrade sheet, and -- unchanged by this fix, verified
    here as a regression guard -- a plain tap starting on the pad must still
    open it.

    Root cause of the original bug: the scene-level 'pointerout' handler
    (meant for "pointer left the canvas") also fires whenever Phaser's
    per-frame processOverOutEvents() sees the pointer move off ANY
    interactive game object underneath it, including the pad (padG,
    setInteractive()) -- not just on canvas-leave. The fix listens on
    'gameout' instead, Phaser's actual InputManager-level canvas-leave
    event. See farm_idle.game.js's 'gameout' handler comment for the full
    root-cause writeup.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        _boot(page, "iPhone_12_tall_contrast")

        pad_screen = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            const cam = scene.cameras.main;
            function worldToScreen(camera, wx, wy) {
                const p0 = camera.getWorldPoint(0, 0);
                const p1 = camera.getWorldPoint(100, 0);
                const p2 = camera.getWorldPoint(0, 100);
                const sx = (wx - p0.x) / (p1.x - p0.x) * 100;
                const sy = (wy - p0.y) / (p2.y - p0.y) * 100;
                return { x: sx, y: sy };
            }
            const pad = scene._computePadLayout();
            return worldToScreen(cam, pad.centerX, pad.centerY);
        }""")

        # Start the joystick drag well away from the pad, then drag THROUGH
        # the pad's on-screen position, sampling farmer position along the
        # way to prove movement never stops.
        start_x, start_y = 195, 300
        page.mouse.move(start_x, start_y)
        page.mouse.down()
        page.wait_for_timeout(50)
        active_after_down = page.evaluate("() => window.__GAME__.scene.scenes[0].joystickActive")
        assert active_after_down, "joystick did not activate at the drag start point"

        farmer_before = page.evaluate("() => { const s = window.__GAME__.scene.scenes[0]; return {x: s.farmer.x, y: s.farmer.y}; }")

        # Drag THROUGH the pad's center and continue PAST it -- the bug this
        # regression-guards only manifests when the pointer actually LEAVES
        # the pad's interactive hit area while still held down (Phaser's
        # object-level 'out' transition, which the old 'pointerout' handler
        # mistook for canvas-leave); stopping exactly at the pad's center and
        # releasing there never triggers that transition and would make this
        # assertion pass even against the unfixed code.
        steps = 20
        end_x = pad_screen["x"] + (pad_screen["x"] - start_x) * 0.3
        end_y = pad_screen["y"] + (pad_screen["y"] - start_y) * 0.3
        farmer_positions = [farmer_before]
        for i in range(1, steps + 1):
            t = i / steps
            x = start_x + (end_x - start_x) * t
            y = start_y + (end_y - start_y) * t
            page.mouse.move(x, y)
            page.wait_for_timeout(30)
            if i in (steps // 2, steps):
                pos = page.evaluate("() => { const s = window.__GAME__.scene.scenes[0]; return { x: s.farmer.x, y: s.farmer.y, joystickActive: s.joystickActive }; }")
                assert pos["joystickActive"], (
                    f"joystickActive went false mid-drag while crossing/passing the upgrade pad "
                    f"(step {i}/{steps}): {pos}"
                )
                farmer_positions.append(pos)

        moved_total = ((farmer_positions[-1]["x"] - farmer_before["x"]) ** 2 + (farmer_positions[-1]["y"] - farmer_before["y"]) ** 2) ** 0.5
        assert moved_total > 50, (
            f"farmer did not keep moving through the drag across and past the upgrade pad: "
            f"before={farmer_before}, samples={farmer_positions}"
        )

        sheet_visible_mid_drag = page.evaluate("() => window.__GAME__.scene.scenes[0].sheetVisible")
        assert not sheet_visible_mid_drag, "upgrade sheet opened mid-drag, before any release"

        # Move back onto the pad's center, still holding, then release there
        # -- the "release over the pad" half of the acceptance criterion.
        page.mouse.move(pad_screen["x"], pad_screen["y"])
        page.wait_for_timeout(50)
        page.mouse.up()
        page.wait_for_timeout(50)
        after_release = page.evaluate("() => { const s = window.__GAME__.scene.scenes[0]; return { sheetVisible: s.sheetVisible, joystickActive: s.joystickActive }; }")
        assert not after_release["sheetVisible"], (
            f"releasing over the upgrade pad after a joystick-started drag incorrectly opened "
            f"the sheet: {after_release}"
        )
        assert not after_release["joystickActive"], (
            f"joystick should be deactivated after a normal pointerup release: {after_release}"
        )

        # Regression guard: a plain tap (no preceding drag) starting on the
        # pad must still open the sheet.
        page.mouse.click(pad_screen["x"], pad_screen["y"])
        page.wait_for_timeout(100)
        after_tap = page.evaluate("() => window.__GAME__.scene.scenes[0].sheetVisible")
        browser.close()

        assert after_tap, (
            f"a plain tap starting on the upgrade pad (no drag) did not open the sheet: "
            f"sheetVisible={after_tap}"
        )
