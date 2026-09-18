"""
Fixed-world market/upgrade-pad tests for farm_idle: split out of the former
monolithic tests/test_farm_idle_real_device.py (Instinct Wire issue #2).

Covers the fixed-world (non-scrolling) stall and upgrade pad introduced
alongside the scrolling world: _computeStallLayout as the single source of
truth for sell detection, tap targeting, and rendering; correctness under
an active world pan/scroll; and behavior while the player/camera are far
offscreen from the stall.
"""
import pytest
from playwright.sync_api import sync_playwright
from farm_idle_test_support import _boot, SHORT_VIEWPORTS, TALL_VIEWPORT

# Old, real-device-proven-wrong sell target: STALL_X + STALL_W/2, STALL_Y +
# STALL_H/2 with the harness's constants (96, 160, 1252, 112).
OLD_FIXED_STALL_CENTER = (176, 1308)


@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", SHORT_VIEWPORTS + [TALL_VIEWPORT])
def test_visible_market_sells_at_every_real_viewport(viewport_width, viewport_height, viewport_name):
    """
    Defect #3 (root cause), functional/black-box form: teleporting the
    farmer to wherever the market is ACTUALLY RENDERED (read from the live
    scene, not a hardcoded coordinate) must trigger a sale, at every real
    viewport -- short ones where the old bug made this impossible, and the
    tall one prior testing used where it happened to work by coincidence.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": viewport_width, "height": viewport_height},
            has_touch=True,
            is_mobile=True,
        )
        _boot(page, viewport_name)

        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            const plot = scene.plots[0];
            plot.readyAt = scene.time.now - 1;
            scene._harvestPlot(0);  // guaranteed to succeed: fresh carry stack

            const stall = scene._computeStallLayout();
            scene.farmer.x = stall.centerX;
            scene.farmer.y = stall.centerY;

            const coinsBefore = scene.coins;
            scene.update(scene.time.now, 16);

            return {
                stall,
                coinsBefore,
                coinsAfter: scene.coins,
                carryAfter: scene.carrySprites.length,
                stallGRenderedY: scene.stallG ? scene.stallG.y : null,
            };
        }""")

        browser.close()

        assert result["coinsAfter"] > result["coinsBefore"], (
            f"{viewport_name} ({viewport_width}x{viewport_height}): selling at the LIVE rendered "
            f"market position (centerY={result['stall']['centerY']:.1f}) did not increase coins "
            f"({result['coinsBefore']} -> {result['coinsAfter']}). Rendered stallG.y="
            f"{result['stallGRenderedY']}, computed stall={result['stall']}"
        )
        assert result["carryAfter"] == 0, "Carry stack should be empty after a successful sale"



@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", SHORT_VIEWPORTS)
def test_old_fixed_stall_target_no_longer_sells_and_diverges_from_real_position(
    viewport_width, viewport_height, viewport_name
):
    """
    Defect #3, negative/regression-hardening form: at short viewports the
    real market position must land FAR from the old hardcoded
    (STALL_X+STALL_W/2, STALL_Y+STALL_H/2) = (176, 1308) -- proving this
    viewport genuinely exercises the drift, not a near-miss coincidence like
    390x844's 58px-vs-60px-radius near-pass. And teleporting the farmer to
    that OLD position must NOT sell, which would catch any regression that
    reintroduces a fixed-constant sell target.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": viewport_width, "height": viewport_height},
            has_touch=True,
            is_mobile=True,
        )
        _boot(page, viewport_name)

        result = page.evaluate("""({oldX, oldY}) => {
            const scene = window.__GAME__.scene.scenes[0];
            const plot = scene.plots[0];
            plot.readyAt = scene.time.now - 1;
            scene._harvestPlot(0);

            const stall = scene._computeStallLayout();

            scene.farmer.x = oldX;
            scene.farmer.y = oldY;
            const coinsBefore = scene.coins;
            scene.update(scene.time.now, 16);

            return {
                stall,
                coinsBefore,
                coinsAfter: scene.coins,
                carryAfter: scene.carrySprites.length,
            };
        }""", {"oldX": OLD_FIXED_STALL_CENTER[0], "oldY": OLD_FIXED_STALL_CENTER[1]})

        browser.close()

        import math
        delta = math.hypot(
            result["stall"]["centerX"] - OLD_FIXED_STALL_CENTER[0],
            result["stall"]["centerY"] - OLD_FIXED_STALL_CENTER[1],
        )
        assert delta > 100, (
            f"{viewport_name} ({viewport_width}x{viewport_height}): expected the real rendered "
            f"stall center to diverge sharply (>100px) from the old fixed (176,1308) target to "
            f"prove this viewport exercises the drift, got only {delta:.1f}px -- "
            f"real={result['stall']}"
        )
        assert result["coinsAfter"] == result["coinsBefore"], (
            f"{viewport_name}: selling at the OLD fixed (STALL_X+STALL_W/2, STALL_Y+STALL_H/2) "
            f"position unexpectedly succeeded ({result['coinsBefore']} -> {result['coinsAfter']}) "
            f"-- this should be unreachable now that sell-detection reads the live computed layout"
        )
        # Not asserting an exact count: defect #5's burst fix means a single
        # harvest adds HARVEST_BURST_SIZE goods, not exactly one. The point
        # of this assertion is unchanged -- nothing was silently lost.
        assert result["carryAfter"] > 0, "Crop(s) should still be carried, not silently lost"



@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", SHORT_VIEWPORTS + [TALL_VIEWPORT])
def test_upgrade_pad_real_tap_opens_sheet_after_world_scroll(viewport_width, viewport_height, viewport_name):
    """Section D sub-dispatch 3 required proof: the upgrade pad is now a fixed
    WORLD entity (_computePadLayout()), not HUD-relative. A real tap at the
    pad's actual on-screen position must still open the upgrade sheet after
    the world camera has scrolled both horizontally and vertically away from
    its boot position -- proving input hit-testing tracks the pad's real
    rendered position under camera pan, not a stale/precomputed one.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": viewport_width, "height": viewport_height}, has_touch=True, is_mobile=True
        )
        _boot(page, viewport_name)

        # Force nonzero horizontal AND vertical world scroll by moving the
        # farmer to a position offset from (but near) the pad's own fixed
        # world position -- this guarantees the pad stays reachable on
        # screen after the camera follows (moving the farmer to an
        # arbitrary far-away point, e.g. deep into the world, can legitimately
        # scroll the pad itself off screen at smaller viewports, which would
        # make "tap the pad" meaningless -- nothing can tap what isn't
        # rendered anywhere on screen).
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

            // True world->screen conversion, sampled from the camera's own
            // screen->world transform (camera.getWorldPoint) and inverted --
            // NOT the naive (worldX - scrollX) * zoom shortcut, which is
            // wrong whenever the camera's default centered origin (0.5, 0.5)
            // isn't separately accounted for (true for this game's main
            // camera, which is never centerOn'd -- it just follows the
            // farmer). Verified technique, reused from the coin-flight fix.
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
                sheetVisibleBefore: scene.sheetVisible,
            };
        }""")

        assert tap_point["worldScrollX"] > 50 and tap_point["worldScrollY"] > 50, (
            f"{viewport_name}: world camera didn't scroll enough to be a meaningful proof: "
            f"scrollX={tap_point['worldScrollX']}, scrollY={tap_point['worldScrollY']}"
        )
        assert not tap_point["sheetVisibleBefore"], "sheet should start closed"

        page.touchscreen.tap(tap_point["screenX"], tap_point["screenY"])
        page.wait_for_timeout(100)

        sheet_visible = page.evaluate("() => window.__GAME__.scene.scenes[0].sheetVisible")
        browser.close()

        assert sheet_visible, (
            f"{viewport_name} ({viewport_width}x{viewport_height}): real tap at the pad's actual "
            f"screen position ({tap_point['screenX']:.1f}, {tap_point['screenY']:.1f}) after world "
            f"scroll ({tap_point['worldScrollX']:.1f}, {tap_point['worldScrollY']:.1f}) did not open "
            f"the upgrade sheet -- the pad's real hit area isn't tracking its rendered position "
            f"under camera pan"
        )



@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", SHORT_VIEWPORTS + [TALL_VIEWPORT])
def test_market_real_interaction_after_world_scroll(viewport_width, viewport_height, viewport_name):
    """Section D sub-dispatch 3 required proof: the market/stall is now a
    fixed WORLD entity (_computeStallLayout()), not HUD-relative. A real
    harvest-carry-sell cycle -- farmer walked into magnet range of a ready
    plot via REAL held joystick input (harvest triggers through the actual
    per-frame magnet-proximity path, _updateMagnet(), not a direct
    _harvestPlot() call), then walked into magnet range of the market's
    ACTUAL rendered position the same way (sale triggers through the same
    real per-frame path, not a manual scene.update() call) -- must still
    work after the world camera has scrolled both horizontally and
    vertically away from boot.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": viewport_width, "height": viewport_height}, has_touch=True, is_mobile=True
        )
        _boot(page, viewport_name)

        # Force nonzero horizontal AND vertical world scroll away from boot,
        # then place the farmer just outside a ready plot's magnet radius
        # (arrange -- the interaction under test starts from here, driven
        # entirely by real input from this point on).
        #
        # Pin every OTHER plot's readyAt far into the future: this test's
        # own real-time budget (two ~600ms settle waits plus up to two
        # 1500ms drag holds) sits close enough to CROP_GROW_MS (4000ms)
        # that, without this, another plot can naturally finish regrowing
        # mid-test and get auto-harvested via magnet proximity as the
        # farmer's drag path walks near it -- filling the carry stack
        # before it ever reaches the SPECIFIC plot this test means to
        # harvest, and making plot[0].harvested falsely read false. Found
        # via a reproducible (3/3) failure at 390x844 during this branch's
        # boot-framing change (which itself turned out unrelated -- the
        # test was already this fragile, the change's timing just tipped
        # it over) and isolated by re-running against the pre-change commit.
        setup = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            scene.plots.forEach((p, i) => { if (i !== 0) p.readyAt = scene.time.now + 999999; });
            const plot = scene.plots[0];
            plot.readyAt = scene.time.now - 1;
            const plotCenterX = plot.x + 48, plotCenterY = plot.y + 48;
            scene.farmer.x = plotCenterX - 100;
            scene.farmer.y = plotCenterY;
            return { plotCenterX, plotCenterY };
        }""")
        page.wait_for_timeout(600)

        candidates = [
            (viewport_width * 0.5, viewport_height * 0.5),
            (viewport_width * 0.5, viewport_height * 0.15),
            (viewport_width * 0.15, viewport_height * 0.5),
        ]

        def real_drag(ddx, ddy, hold_ms):
            active = False
            cx = cy = None
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
                f"{viewport_name}: joystick did not activate at any candidate screen point "
                f"{candidates}"
            )
            page.mouse.move(cx + ddx, cy + ddy, steps=5)
            page.wait_for_timeout(hold_ms)
            page.mouse.up()
            page.wait_for_timeout(50)

        # Real held drag: walk right (+x) into the plot's magnet radius (100
        # units to cover, well within a 1500ms hold at MOVE_SPEED).
        real_drag(150, 0, 1500)

        harvest_state = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            return {
                harvested: scene.plots[0].harvested,
                carryCount: scene.carrySprites.length,
                farmerX: scene.farmer.x, farmerY: scene.farmer.y,
            };
        }""")
        assert harvest_state["harvested"] and harvest_state["carryCount"] > 0, (
            f"{viewport_name}: real joystick-driven approach into plot magnet range did not "
            f"trigger a harvest via _updateMagnet(): {harvest_state}"
        )

        # Now place the farmer just outside the stall's magnet radius
        # (arrange for phase 2), confirming world scroll is still
        # meaningfully nonzero, then real-drag into range to sell.
        setup2 = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            const cam = scene.cameras.main;
            const stall = scene._computeStallLayout();
            scene.farmer.x = stall.centerX - 100;
            scene.farmer.y = stall.centerY;
            return { stall, coinsBefore: scene.coins };
        }""")
        page.wait_for_timeout(600)

        world_scroll_before_sell = page.evaluate("() => { const c = window.__GAME__.scene.scenes[0].cameras.main; return { x: c.scrollX, y: c.scrollY }; }")

        real_drag(150, 0, 1500)

        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            return { coinsAfter: scene.coins, carryAfter: scene.carrySprites.length };
        }""")
        browser.close()

        assert world_scroll_before_sell["x"] > 50 and world_scroll_before_sell["y"] > 50, (
            f"{viewport_name}: world camera didn't scroll enough to be a meaningful proof: "
            f"{world_scroll_before_sell}"
        )
        assert result["coinsAfter"] > setup2["coinsBefore"], (
            f"{viewport_name} ({viewport_width}x{viewport_height}): real joystick-driven approach "
            f"into the market's magnet range (world scroll={world_scroll_before_sell}) did not "
            f"trigger a sale via _updateMagnet() ({setup2['coinsBefore']} -> {result['coinsAfter']})"
        )
        assert result["carryAfter"] == 0, "Carry stack should be empty after a successful sale"



@pytest.mark.slow
def test_stall_and_pad_hold_fixed_world_position_under_pan():
    """Section D sub-dispatch 3 required proof: the market/stall and upgrade
    pad's own WORLD coordinates (scene.stallG.x/y, scene.padG.x/y) must be
    genuinely constant across a camera pan -- as fixed world entities they
    should only ever move on-screen by the camera's own pan delta, never in
    their own coordinate space. This is a direct object-property assertion,
    appropriate here because "does this world object's world position stay
    constant" IS the property under test (unlike a cross-camera rendering
    check, where an object's own coordinate can be correct while it still
    renders in the wrong camera).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        _boot(page, "iPhone_12_tall_contrast")

        before = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            return {
                stallX: scene.stallG.x, stallY: scene.stallG.y,
                padX: scene.padG.x, padY: scene.padG.y,
            };
        }""")

        page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            scene.farmer.x = 1300;
            scene.farmer.y = 1800;
        }""")
        page.wait_for_timeout(600)

        after = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            const cam = scene.cameras.main;
            return {
                stallX: scene.stallG.x, stallY: scene.stallG.y,
                padX: scene.padG.x, padY: scene.padG.y,
                worldScrollX: cam.scrollX, worldScrollY: cam.scrollY,
            };
        }""")
        browser.close()

        assert after["worldScrollX"] > 50 and after["worldScrollY"] > 50, (
            f"world camera didn't pan enough to be a meaningful proof: "
            f"scrollX={after['worldScrollX']}, scrollY={after['worldScrollY']}"
        )
        assert before["stallX"] == after["stallX"] and before["stallY"] == after["stallY"], (
            f"stall world position changed under camera pan: "
            f"before=({before['stallX']}, {before['stallY']}) after=({after['stallX']}, {after['stallY']})"
        )
        assert before["padX"] == after["padX"] and before["padY"] == after["padY"], (
            f"pad world position changed under camera pan: "
            f"before=({before['padX']}, {before['padY']}) after=({after['padX']}, {after['padY']})"
        )



@pytest.mark.slow
def test_market_sell_works_while_offscreen():
    """Section D sub-dispatch 3 required proof: selling at the market must
    work even when the market's fixed world position is scrolled entirely
    off screen -- proving sell detection is a pure world-space proximity
    check (via _computeStallLayout()), independent of whether the camera
    currently happens to be rendering that part of the world. A
    viewport-relative implementation would have silently broken this case;
    a fixed-world one handles it for free.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        _boot(page, "iPhone_12_tall_contrast")

        # Scroll the world camera far from the stall's fixed world position
        # (opposite corner of the world) and let real frames settle there.
        page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            scene.farmer.x = 1350;
            scene.farmer.y = 1900;
        }""")
        page.wait_for_timeout(600)

        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            const cam = scene.cameras.main;
            const stall = scene._computeStallLayout();

            // Confirm the stall is genuinely NOT in the currently-rendered
            // world view before doing anything else. 160/112 are STALL_W/
            // STALL_H (the stall's own fixed pixel dimensions).
            const view = cam.worldView;
            const stallOnScreen = (
                stall.x + 160 > view.x && stall.x < view.x + view.width &&
                stall.y + 112 > view.y && stall.y < view.y + view.height
            );

            // Harvest, then teleport the farmer directly to the stall's real
            // world position and trigger the sale synchronously -- no
            // further real frame renders happen between here and reading
            // the result, so cam.scrollX/Y (and therefore worldView) below
            // still reflect the far-away, stall-offscreen view captured
            // just above.
            const plot = scene.plots[0];
            plot.readyAt = scene.time.now - 1;
            scene._harvestPlot(0);

            scene.farmer.x = stall.centerX;
            scene.farmer.y = stall.centerY;
            const coinsBefore = scene.coins;
            scene.update(scene.time.now, 16);

            return {
                stallOnScreenBeforeSale: stallOnScreen,
                coinsBefore, coinsAfter: scene.coins,
                carryAfter: scene.carrySprites.length,
                worldViewAfterSale: cam.worldView,
                stall,
            };
        }""")
        browser.close()

        assert not result["stallOnScreenBeforeSale"], (
            f"stall was already on-screen before the sale -- not a meaningful offscreen proof. "
            f"stall={result['stall']}, worldView={result['worldViewAfterSale']}"
        )
        assert result["coinsAfter"] > result["coinsBefore"], (
            f"selling at the offscreen market did not increase coins "
            f"({result['coinsBefore']} -> {result['coinsAfter']})"
        )
        assert result["carryAfter"] == 0, "Carry stack should be empty after a successful offscreen sale"
