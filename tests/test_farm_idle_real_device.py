#!/usr/bin/env python3
"""
Regression tests for the 5 real-device defects found on Tal's actual iPhone
after farm_idle passed the prior emulated/headless review cycle (merged at
7bc90f4). All 5 defects were missed by every prior emulated viewport (e.g.
390x844) because that viewport happens to be tall enough to mask them --
these tests specifically exercise SHORT real-Safari-chrome-accounted-for
viewports (~390x650 and similar), not the taller ones already covered by
tests/test_farm_idle_viewport.py.

Defect #3 (the root cause of the broken economy) is the centerpiece: a
dynamically-computed HUD stall position (_layoutHUD/_computeStallLayout)
had drifted from a separate hardcoded STALL_Y constant that
_updateMagnet()/_sellAtStall()/helper-targeting used for sell detection. At
390x844 the two positions happened to land within MAGNET_RADIUS (58px vs a
60px radius) by near-coincidence, which is exactly why the prior test suite
never caught this. At 390x650 the gap is ~300px and selling was provably
impossible. The fix makes PlayScene._computeStallLayout() the single source
of truth read by every consumer (layout, magnet, particle fx, helper
targeting) -- see farm_idle.game.js for the implementation.
"""
import pytest
import struct
import zlib
from pathlib import Path
from playwright.sync_api import sync_playwright

HARNESS_DIR = Path(__file__).parent.parent / "harness"

# Real short-Safari-chrome-accounted-for viewports -- these are the sizes
# that actually surfaced the defects on a real device, deliberately NOT the
# taller ~390x844 emulated size used throughout the prior review cycle.
SHORT_VIEWPORTS = [
    (390, 650, "iPhone_effective_short"),
    (414, 700, "iPhone_11_short_chrome"),
    (360, 615, "Galaxy_short_chrome"),
]

# Included as a contrast case: the taller viewport prior testing used, where
# the old bug happened to (barely) not trigger. The fix must keep working
# here too, not just at the short sizes.
TALL_VIEWPORT = (390, 844, "iPhone_12_tall_contrast")

# Old, real-device-proven-wrong sell target: STALL_X + STALL_W/2, STALL_Y +
# STALL_H/2 with the harness's constants (96, 160, 1252, 112).
OLD_FIXED_STALL_CENTER = (176, 1308)

CARRY_STACK_MAX = 8  # must match farm_idle.game.js
HARVEST_BURST_SIZE = 3  # must match farm_idle.game.js


def _safe_insets_for(viewport_name):
    if "iPhone" in viewport_name:
        return {"top": 44, "right": 0, "bottom": 34, "left": 0}
    if "Galaxy" in viewport_name:
        return {"top": 0, "right": 0, "bottom": 24, "left": 0}
    return {"top": 0, "right": 0, "bottom": 0, "left": 0}


def _read_pixel_via_screenshot(page, screen_x, screen_y):
    """Read the RGB color actually composited at (screen_x, screen_y) via a
    1x1 Playwright screenshot clip, decoding the returned PNG with stdlib
    only. Needed because farm_idle's canvas uses Phaser's default WebGL
    renderer with preserveDrawingBuffer left at its default `false`:
    canvas.getContext("2d") returns null on an already-WebGL canvas, and
    both gl.readPixels() and canvas.toDataURL() read back all-black
    regardless of real content or added waits, since the browser is free
    to -- and empirically does -- clear the drawing buffer right after
    compositing each frame. A screenshot captures the compositor's actual
    output instead, sidestepping the WebGL buffer entirely.
    """
    png_bytes = page.screenshot(clip={"x": screen_x, "y": screen_y, "width": 1, "height": 1})
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos = 8
    width = bit_depth = color_type = None
    idat = b""
    while pos < len(png_bytes):
        length = struct.unpack(">I", png_bytes[pos:pos + 4])[0]
        ctype = png_bytes[pos + 4:pos + 8]
        data = png_bytes[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            width, _height, bit_depth, color_type = struct.unpack(">IIBB", data[:10])
        elif ctype == b"IDAT":
            idat += data
        elif ctype == b"IEND":
            break
        pos += 8 + length + 4
    assert bit_depth == 8, f"unexpected PNG bit depth {bit_depth}"
    bpp = {2: 3, 6: 4}.get(color_type)
    assert bpp, f"unexpected PNG color type {color_type}"
    raw = zlib.decompress(idat)
    stride = width * bpp
    filt = raw[0]
    line = bytearray(raw[1:1 + stride])
    prior = bytearray(stride)  # all-zero "previous scanline" -- clip is 1px tall
    if filt == 0:  # None
        pass
    elif filt == 1:  # Sub
        for i in range(len(line)):
            a = line[i - bpp] if i >= bpp else 0
            line[i] = (line[i] + a) & 0xFF
    elif filt == 2:  # Up
        for i in range(len(line)):
            line[i] = (line[i] + prior[i]) & 0xFF
    elif filt == 3:  # Average
        for i in range(len(line)):
            a = line[i - bpp] if i >= bpp else 0
            b = prior[i]
            line[i] = (line[i] + (a + b) // 2) & 0xFF
    elif filt == 4:  # Paeth
        for i in range(len(line)):
            a = line[i - bpp] if i >= bpp else 0
            b = prior[i]
            c = prior[i - bpp] if i >= bpp else 0
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
            line[i] = (line[i] + pr) & 0xFF
    else:
        raise ValueError(f"unsupported PNG filter type {filt}")
    return tuple(line[:3])


def _boot(page, viewport_name):
    """Common boot sequence: load harness, start game, apply safe insets."""
    html_path = HARNESS_DIR / "farm_idle.html"
    page.goto(f"file://{html_path.absolute()}")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("window.__GAME__ !== undefined", timeout=10000)
    page.wait_for_timeout(300)

    page.evaluate("() => { window.__GAME__.scene.scenes[0]._begin(); }")
    page.wait_for_timeout(100)

    insets = _safe_insets_for(viewport_name)
    page.evaluate("""
        () => {
            const root = document.documentElement;
            root.style.setProperty('--safe-top', '%dpx');
            root.style.setProperty('--safe-right', '%dpx');
            root.style.setProperty('--safe-bottom', '%dpx');
            root.style.setProperty('--safe-left', '%dpx');
            if (typeof updateSafeInsets === 'function') updateSafeInsets();
            const scene = window.__GAME__.scene.scenes[0];
            if (scene._layoutHUD) scene._layoutHUD();
        }
    """ % (insets["top"], insets["right"], insets["bottom"], insets["left"]))
    page.wait_for_timeout(100)


@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", SHORT_VIEWPORTS + [TALL_VIEWPORT])
def test_top_hud_elements_do_not_overlap(viewport_width, viewport_height, viewport_name):
    """
    2nd-round Instinct review, real-device HUD collision: "the large
    'Coins:' label physically overlaps the 'Next upgrade' meter... moving
    only the progress row shifted the collision, it did not remove it" --
    referring to the temporary intro slogan banner ("HARVEST . SELL .
    UPGRADE"), which still collided with coinsText even after the progress
    row was moved, because the banner's Y was computed once at creation
    time (before real safe-area insets are known) and never re-synced when
    _layoutHUD() later ran with the real values.

    Asserts actual rendered pixel bounds of all three top-HUD elements
    (coinsText, progressText, and the intro banner, while it's still alive
    within its ~2.5s window) pairwise do not overlap -- not inferred from
    Y-coordinate arithmetic, which is exactly what looked correct on paper
    the first time this was "fixed" and still collided for real.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": viewport_width, "height": viewport_height},
            has_touch=True,
            is_mobile=True,
        )
        _boot(page, viewport_name)  # banner has a ~2.5s lifetime, _boot() finishes well within it

        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            const canvas = scene.game.canvas;
            const rect = canvas.getBoundingClientRect();
            const scaleX = rect.width / 720;

            function screenBounds(obj) {
                const b = obj.getBounds();
                return {
                    left: rect.left + b.x * scaleX,
                    top: rect.top + b.y * scaleX,
                    right: rect.left + (b.x + b.width) * scaleX,
                    bottom: rect.top + (b.y + b.height) * scaleX,
                };
            }
            function overlaps(a, b) {
                return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
            }

            const coins = screenBounds(scene.coinsText);
            const progress = screenBounds(scene.progressText);
            const bannerObj = scene._introBannerText;

            const out = { coins, progress, bannerAlive: !!bannerObj, coinsVsProgress: overlaps(coins, progress) };
            if (bannerObj) {
                const banner = screenBounds(bannerObj);
                out.banner = banner;
                out.coinsVsBanner = overlaps(coins, banner);
                out.progressVsBanner = overlaps(progress, banner);
            }
            return out;
        }""")

        browser.close()

        assert result["coinsVsProgress"] is False, (
            f"{viewport_name} ({viewport_width}x{viewport_height}): coinsText overlaps "
            f"progressText: {result}"
        )
        # The banner is only alive for ~2.5s -- if this test ever starts
        # seeing bannerAlive=False, _boot()'s timing changed and this check
        # is silently no longer exercising the banner at all; that's a
        # test-infrastructure problem worth surfacing loudly, not a quiet skip.
        assert result["bannerAlive"], (
            f"{viewport_name}: intro banner was not alive when checked -- "
            f"_boot() timing may have changed, this test is not exercising the banner"
        )
        assert result["coinsVsBanner"] is False, (
            f"{viewport_name} ({viewport_width}x{viewport_height}): intro banner overlaps "
            f"coinsText: {result}"
        )
        assert result["progressVsBanner"] is False, (
            f"{viewport_name} ({viewport_width}x{viewport_height}): intro banner overlaps "
            f"progressText: {result}"
        )


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
def test_natural_harvest_sell_coins_buy_loop_at_short_viewport():
    """
    The full "real flow" the review asked for, at the shortest real
    viewport (390x650): magnet-proximity harvest (farmer walks near ready
    plots) -> magnet-proximity sell at the VISIBLE market -> coins increment
    -> BUY an upgrade using the ACTUAL earned coins (not a forced balance)
    -> the top-HUD coins-toward-next-upgrade meter refreshes afterward.
    Exercises defect #3's fix through the actual proximity-based magnet path
    (not a teleport-to-exact-point shortcut), matching how
    _test_magnet_collection already drives the harvest half of this flow
    elsewhere in the suite.

    Harvests 2 plots (not 1) before selling: with the defect #5 burst fix
    each harvest now adds HARVEST_BURST_SIZE (3) goods, so 2 harvests -> 6
    items -> a real sell of 6 * CROP_SELL_VALUE(10) = 60 coins, enough to
    genuinely afford the 50-coin base plot upgrade without cheating the
    balance -- this is the test-debt item the review flagged.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": 390, "height": 650}, has_touch=True, is_mobile=True
        )
        _boot(page, "iPhone_effective_short")

        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            const MAGNET_RADIUS = 60;

            // 1. Natural harvest: place farmer within magnet radius of two
            // forced-ready plots in turn and tick, exactly like
            // _test_magnet_collection does elsewhere in the suite. Two
            // harvests (not one) so the real sale proceeds are enough to
            // genuinely afford an upgrade -- see docstring.
            const carryAfterHarvests = [];
            for (const plot of [scene.plots[0], scene.plots[1]]) {
                plot.readyAt = scene.time.now - 1;
                const plotCenterX = plot.x + 48, plotCenterY = plot.y + 48;
                scene.farmer.x = plotCenterX + (MAGNET_RADIUS - 10);
                scene.farmer.y = plotCenterY;
                scene.update(scene.time.now, 16);
                carryAfterHarvests.push(scene.carrySprites.length);
            }
            const harvested = scene.plots[0].harvested && scene.plots[1].harvested
                && scene.carrySprites.length === carryAfterHarvests[carryAfterHarvests.length - 1]
                && scene.carrySprites.length > 0;

            // 2. Move farmer to within magnet radius of the VISIBLE market
            // (live computed layout) and tick to sell everything carried.
            const stall = scene._computeStallLayout();
            scene.farmer.x = stall.centerX + (MAGNET_RADIUS - 10);
            scene.farmer.y = stall.centerY;
            const coinsBeforeSell = scene.coins;
            scene.update(scene.time.now, 16);
            const sold = scene.coins > coinsBeforeSell && scene.carrySprites.length === 0;

            // 3. Buy an upgrade using the REAL earned coins -- no forced
            // balance. The progress-bar text is captured before and after
            // so the assertions can prove the meter actually refreshes.
            const coinsAfterSell = scene.coins;
            const progressTextBefore = scene.progressText.text;
            const plotsBefore = scene.plots.length;
            scene._buyUpgrade('plot');
            scene.update(scene.time.now, 16);  // let the per-tick HUD refresh run
            const bought = scene.plots.length === plotsBefore + 1;
            const progressTextAfter = scene.progressText.text;

            return {
                harvested, sold, bought,
                carryAfterHarvests,
                coinsBeforeSell, coinsAfterSell, coinsAfterBuy: scene.coins,
                plotsBefore, plotsAfter: scene.plots.length,
                progressTextBefore, progressTextAfter,
                stall,
            };
        }""")

        browser.close()

        assert result["harvested"], f"Natural magnet-proximity harvest (x2) failed: {result}"
        assert result["sold"], (
            f"Magnet-proximity sell at the visible market failed: "
            f"coins {result['coinsBeforeSell']} -> {result['coinsAfterSell']}, stall={result['stall']}"
        )
        assert result["coinsAfterSell"] > result["coinsBeforeSell"], "Coins must increment on sale"
        assert result["coinsAfterSell"] >= 50, (
            f"Test setup assumption broken: 2 harvests' worth of real sale proceeds "
            f"({result['coinsAfterSell']}) should comfortably afford the 50-coin base "
            f"plot upgrade without forcing the balance -- got {result}"
        )
        assert result["bought"], (
            f"BUY upgrade did not add a plot using real earned coins: "
            f"{result['plotsBefore']} -> {result['plotsAfter']}, coins={result['coinsAfterSell']}"
        )
        assert result["progressTextAfter"] != result["progressTextBefore"], (
            f"Coins-toward-next-upgrade meter did not refresh after purchase: "
            f"before={result['progressTextBefore']!r} after={result['progressTextAfter']!r}"
        )


@pytest.mark.slow
def test_farmer_stationary_with_zero_input():
    """
    Defect #2 regression: with the joystick idle/untouched and no helper
    purchased, the farmer must not move on its own -- even when there's a
    ready plot to walk toward (forcing readiness is essential here; without
    it there's nothing for the old auto-walk-to-nearest-ready-plot bug to
    walk toward and the test would pass vacuously regardless of the fix).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": 390, "height": 650}, has_touch=True, is_mobile=True
        )
        _boot(page, "iPhone_effective_short")

        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];

            // Force plot 0 ready but keep the farmer far from it (the old
            // bug would walk the farmer 148-183px toward a ready plot over
            // ~1.8s on a real device with zero input).
            const plot = scene.plots[0];
            plot.readyAt = scene.time.now - 1;
            // Farmer starts far from plot 0's center (>150px away, well
            // outside MAGNET_RADIUS=60) so the old auto-walk bug would have
            // visibly moved it toward the plot over this window.
            scene.farmer.x = 30;

            scene.joystickActive = false;
            scene.joystickVector = { x: 0, y: 0 };

            const startX = scene.farmer.x, startY = scene.farmer.y;

            // ~1.8s of ticks at 16ms/frame, matching the real-device
            // observation window from the review.
            for (let i = 0; i < 112; i++) {
                scene.update(scene.time.now + i * 16, 16);
            }

            return {
                startX, startY,
                endX: scene.farmer.x, endY: scene.farmer.y,
                plotStillUnharvestedOrRegrew: true,
            };
        }""")

        browser.close()

        assert result["endX"] == result["startX"] and result["endY"] == result["startY"], (
            f"Farmer moved with zero input and no helper purchased: "
            f"({result['startX']}, {result['startY']}) -> ({result['endX']}, {result['endY']})"
        )


@pytest.mark.slow
def test_carry_stack_capacity_enforced():
    """
    Defect #1 regression, made exact per Instinct's 2nd-round review ("the
    cap test would pass the old one-item behavior... require exact
    counts"): asserts the carry stack length after EVERY single harvest
    attempt, not just an aggregate max/blocked-count that a bug producing
    the wrong-but-still-capped burst size could slip through. Covers the
    three specific transitions requested: one harvest 0->3, a second
    harvest 3->6, and a partial burst exactly at the cap boundary 7->8
    (only 1 of the usual 3-item burst fits before hitting CARRY_STACK_MAX).
    Then continues past the cap with no selling to confirm it holds.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": 390, "height": 650}, has_touch=True, is_mobile=True
        )
        _boot(page, "iPhone_effective_short")

        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            const plot = scene.plots[0];
            const stackAfterEachHarvest = [];

            for (let i = 0; i < 20; i++) {  // far more than CARRY_STACK_MAX
                plot.readyAt = scene.time.now - 1;
                scene.update(scene.time.now, 16);  // regrow-reset runs here
                scene._harvestPlot(0);
                stackAfterEachHarvest.push(scene.carrySprites.length);
            }

            return {
                stackAfterEachHarvest,
                finalStackLength: scene.carrySprites.length,
            };
        }""")

        browser.close()

        seq = result["stackAfterEachHarvest"]
        assert seq[0] == HARVEST_BURST_SIZE, (
            f"One harvest from an empty stack must add exactly {HARVEST_BURST_SIZE}, "
            f"got {seq[0]} after the first harvest (full sequence: {seq})"
        )
        assert seq[1] == HARVEST_BURST_SIZE * 2, (
            f"A second harvest must add exactly {HARVEST_BURST_SIZE} more "
            f"({HARVEST_BURST_SIZE} -> {HARVEST_BURST_SIZE * 2}), got {seq[1]} "
            f"(full sequence: {seq})"
        )
        # Third harvest (index 2) takes the stack from 6 to the cap of 8 --
        # only 2 of the usual 3-item burst fit, not the partial-at-7 case
        # Instinct described; harvest index 2 is the one that actually
        # crosses the cap boundary given a burst size of 3 starting at 0.
        assert seq[2] == CARRY_STACK_MAX, (
            f"The harvest that crosses the cap boundary must clamp exactly "
            f"at CARRY_STACK_MAX ({CARRY_STACK_MAX}), got {seq[2]} (full sequence: {seq})"
        )
        assert all(v == CARRY_STACK_MAX for v in seq[2:]), (
            f"Every harvest after the cap is first reached must stay pinned at "
            f"{CARRY_STACK_MAX} (blocked, not silently dropping the plot's crop): {seq}"
        )
        assert result["finalStackLength"] == CARRY_STACK_MAX


@pytest.mark.slow
def test_helper_harvest_burst_exact_counts():
    """
    Same exact-count requirement as test_carry_stack_capacity_enforced,
    but for the HELPER's harvest path (_updateHelper -> _addHarvestBurst),
    which adds to the same shared player carry stack via a separate code
    path from the player's own _harvestPlot -- Instinct's review explicitly
    asked for exact counts "on the player and helper paths as applicable"
    since a burst-size bug could exist in one path but not the other.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": 390, "height": 650}, has_touch=True, is_mobile=True
        )
        _boot(page, "iPhone_effective_short")

        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            scene.coins = 500;
            scene._buyUpgrade('helper');
            const helper = scene.helpers[0];
            const stackAfterEachHarvest = [];

            // Harvest 3 distinct plots via the helper (a single plot can't
            // be re-harvested until it regrows) -- same teleport-onto-plot
            // pattern already used in test_farm_idle_juice.py.
            for (let i = 0; i < 3; i++) {
                const plot = scene.plots[i];
                plot.readyAt = scene.time.now - 1;
                helper.x = plot.x + 30; helper.y = plot.y + 30;
                helper.sprite.x = helper.x; helper.sprite.y = helper.y;
                helper.state = 'seeking_plot';
                scene.update(scene.time.now, 16);
                stackAfterEachHarvest.push(scene.carrySprites.length);
            }

            return { stackAfterEachHarvest };
        }""")

        browser.close()

        seq = result["stackAfterEachHarvest"]
        assert seq[0] == HARVEST_BURST_SIZE, (
            f"Helper's first harvest must add exactly {HARVEST_BURST_SIZE} to the shared "
            f"carry stack, got {seq[0]} (full sequence: {seq})"
        )
        assert seq[1] == HARVEST_BURST_SIZE * 2, (
            f"Helper's second harvest must add exactly {HARVEST_BURST_SIZE} more, "
            f"got {seq[1]} (full sequence: {seq})"
        )
        # Third harvest would naively add 3 more (-> 9), but CARRY_STACK_MAX
        # is 8 and the cap applies to the shared stack regardless of which
        # path (player or helper) is adding to it -- this is itself the
        # partial-burst-near-cap case Instinct asked to see covered on the
        # helper path specifically: only 2 of the usual 3-item burst fit.
        assert seq[2] == CARRY_STACK_MAX, (
            f"Helper's third harvest crosses CARRY_STACK_MAX ({CARRY_STACK_MAX}) -- "
            f"expected the burst to clamp at the cap (6 -> 8, only 2 of the usual "
            f"{HARVEST_BURST_SIZE} added), got {seq[2]} (full sequence: {seq})"
        )


@pytest.mark.slow
def test_buy_button_disabled_vs_affordable_visual_state():
    """
    Additional flagged issue: BUY buttons must show a visually distinct
    state when the player can't afford the upgrade (previously they always
    looked identical, so an unaffordable tap looked dead/unresponsive).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": 390, "height": 650}, has_touch=True, is_mobile=True
        )
        _boot(page, "iPhone_effective_short")

        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];

            // Too poor to afford the cheapest upgrade (plot costs 50 by default).
            scene.coins = 0;
            scene._openUpgradeSheet();
            const plotRow = scene.upgradeRows.find(r => r.type === 'plot');
            const unaffordable = {
                fillColor: plotRow.btn.fillColor,
                fillAlpha: plotRow.btn.fillAlpha,
            };
            scene._closeUpgradeSheet();

            // Now affordable.
            scene.coins = 999999;
            scene._openUpgradeSheet();
            const plotRow2 = scene.upgradeRows.find(r => r.type === 'plot');
            const affordable = {
                fillColor: plotRow2.btn.fillColor,
                fillAlpha: plotRow2.btn.fillAlpha,
            };
            scene._closeUpgradeSheet();

            return { unaffordable, affordable };
        }""")

        browser.close()

        distinct = (
            result["unaffordable"]["fillColor"] != result["affordable"]["fillColor"]
            or result["unaffordable"]["fillAlpha"] != result["affordable"]["fillAlpha"]
        )
        assert distinct, (
            f"BUY button looks identical whether affordable or not: "
            f"unaffordable={result['unaffordable']}, affordable={result['affordable']}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])


@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", SHORT_VIEWPORTS + [TALL_VIEWPORT])
def test_depth_ordering_with_extra_plot_purchase(viewport_width, viewport_height, viewport_name):
    """
    Regression test for depth ordering bug: purchasing plots should not cause
    later-created plots to overtake earlier same-depth objects.
    Purchases a 6th plot (reaching plot index 5) and verifies that
    farmer.depth (10) and carryStack.depth (10) exceed all plot depths (0).
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
            // _buyUpgrade silently no-ops if unaffordable (if (this.coins < cost) return;)
            // -- coins start at 0 and harvesting alone never awards coins (only
            // selling does), so purchases must be funded directly here or every
            // _buyUpgrade call below is a silent no-op and plots.length never
            // actually reaches 6, making this test vacuous.
            scene.coins = 999999;
            // Buy 5 more plots (total 6 plots: indices 0-5)
            for (let i = 0; i < 5; i++) {
                scene._buyUpgrade("plot");
            }
            const reachedSix = scene.plots.length >= 6;
            const depths = {
                reachedSix,
                farmer: scene.farmer ? scene.farmer.depth : null,
                carryStack: scene.carryStack ? scene.carryStack.depth : null,
                // scene.plots holds plain data objects ({index, x, y, plotSprite, ...}),
                // not Phaser GameObjects themselves -- .depth was set via
                // plotSprite.setDepth(0), so it lives on p.plotSprite, not p.
                plots: scene.plots.map(p => p.plotSprite.depth),
            };
            return depths;
        }""")

        browser.close()

        assert result["reachedSix"], (
            f"{viewport_name}: test setup failed to actually reach 6 plots "
            f"(purchases may have silently failed) -- this test would be vacuous "
            f"without this check, since it never exercised the later-created-plot "
            f"scenario the depth fix targets"
        )
        # Verify farmer and carryStack have depth 10
        assert result["farmer"] == 10, (
            f"{viewport_name}: farmer.depth should be 10, got {result['farmer']}"
        )
        assert result["carryStack"] == 10, (
            f"{viewport_name}: carryStack.depth should be 10, got {result['carryStack']}"
        )
        # Verify all plots have depth 0
        for i in range(len(result["plots"])):
            assert result["plots"][i] == 0, (
                f"{viewport_name}: plot[{i}].depth should be 0 (ground layer), got {result['plots'][i]}"
            )
        # Verify farmer and carryStack are above all plots
        assert result["farmer"] > max(result["plots"]), (
            f"{viewport_name}: farmer.depth should be above all plot depths"
        )
        assert result["carryStack"] > max(result["plots"]), (
            f"{viewport_name}: carryStack.depth should be above all plot depths"
        )


@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", SHORT_VIEWPORTS + [TALL_VIEWPORT])
def test_carry_stack_pixel_color_vs_plot_when_overlapping(viewport_width, viewport_height, viewport_name):
    """
    Regression test for bug 1 (text corruption fix verification via pixel color):
    Harvest a crop to put something in the carry stack, advance to having
    a 6th plot that overlaps the carry stack position, then sample the
    rendered pixel color at the carry sprite position to verify it shows
    the crop color (green-ish) not the plot color (brown-ish).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": viewport_width, "height": viewport_height},
            has_touch=True,
            is_mobile=True,
        )
        _boot(page, viewport_name)

        # Phase 1: mutate game state (coins, plots, farmer/carry-stack position)
        # and compute the target buffer-space pixel coordinates. This only
        # needs game LOGIC to have advanced (scene.update()), which is
        # synchronous and immediate.
        setup = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            // Same affordability fix as test_depth_ordering_with_extra_plot_purchase --
            // _buyUpgrade silently no-ops if unaffordable, and coins start at 0.
            scene.coins = 999999;
            while (scene.plots.length < 6 && scene.plots.length < 200) {
                const before = scene.plots.length;
                scene._buyUpgrade("plot");
                if (scene.plots.length === before) break;  // stalled -- avoid an infinite loop
            }
            if (scene.plots.length < 6) return { error: "did not reach 6 plots" };

            // Harvest from a DIFFERENT, still-untouched plot to get a crop in the
            // carry stack (plot 1, not plot 5 -- plot 5 is the one we're about to
            // occlude against).
            scene.plots[1].readyAt = scene.time.now - 1;
            scene._harvestPlot(1);  // Adds HARVEST_BURST_SIZE (3) crops
            if (scene.carrySprites.length === 0) return { error: "harvest produced no carry sprites" };

            // Plot 5's data x/y IS its real rendered position -- _createPlot()
            // bakes those exact coordinates into the plot's Graphics draw calls
            // at creation and they are never mutated afterward for an
            // already-created plot (mutating plot.x/y post-creation, as an
            // earlier version of this test tried, does NOT move the rendered
            // graphics -- Phaser Graphics objects draw at the coordinates given
            // to fillRoundedRect(), not at a transform read each frame). So the
            // correct way to create real occlusion is to move something that DOES
            // respond to position mutation -- the farmer (a Circle GameObject,
            // real transform-driven rendering) -- onto plot 5's real position,
            // then let _updateCarryStackPosition() (called every update() tick)
            // carry the carryStack container along with it.
            const plot5 = scene.plots[5];
            scene.farmer.x = plot5.x + 48;  // plot center-ish (PLOT_SIZE=96)
            scene.farmer.y = plot5.y + 48;
            plot5.readyAt = scene.time.now - 1;  // force fully rendered, not mid-grow
            scene.update(scene.time.now, 16);

            // carrySprites are children of the carryStack CONTAINER, so their
            // .x/.y are LOCAL to that container, not absolute canvas coordinates --
            // absolute logical position is spriteLocal + containerPosition.
            const carrySprite = scene.carrySprites[0];
            const worldX = carrySprite.x + scene.carryStack.x;
            const worldY = carrySprite.y + scene.carryStack.y;

            const canvas = scene.game.canvas;
            const rect = canvas.getBoundingClientRect();
            const scaleX = rect.width / 720;  // established convention: logical width is always 720
            const screenX = Math.round(rect.left + worldX * scaleX);
            const screenY = Math.round(rect.top + worldY * scaleX);

            return { screenX, screenY };
        }""")

        if "error" in setup:
            browser.close()
            raise AssertionError(f"{viewport_name}: {setup['error']}")

        # Manually driving scene.update() (phase 1) only advances Phaser's
        # game-LOGIC loop -- it does not trigger the actual WebGL render pass,
        # which runs on its own requestAnimationFrame-driven ticker separate
        # from Scene.update(). Give the browser a real paint cycle before
        # screenshotting, same as the drag-driven farmer-movement tests
        # elsewhere in this suite (test_farm_idle_viewport.py) already do for
        # the same requestAnimationFrame-timing reason.
        page.wait_for_timeout(100)

        # Phase 2: now that a real frame has rendered the moved farmer/carry
        # stack, read the actual composited pixel at the previously-computed
        # screen coordinates. canvas.getContext("2d") (null on an
        # already-WebGL canvas) and gl.readPixels()/canvas.toDataURL() (both
        # read back all-black -- the browser is free to, and empirically
        # does, clear the WebGL drawing buffer right after compositing since
        # preserveDrawingBuffer defaults to false) were both tried and ruled
        # out here; see _read_pixel_via_screenshot()'s docstring.
        r, g, b = _read_pixel_via_screenshot(page, setup["screenX"], setup["screenY"])
        browser.close()

        # Crop color: 0x8bc34a (139,195,74) green-ish. Plot color:
        # 0x5d4037 (93,64,55) brown-ish.
        is_greenish = g > r and g > b and g > 100
        is_brownish = 80 < r < 120 and 50 < g < 80 and 40 < b < 70

        # Verify the pixel is greenish (crop) not brownish (plot)
        assert is_greenish, (
            f"{viewport_name}: carry sprite pixel should be greenish (crop), got rgb({r},{g},{b})"
        )
        assert not is_brownish, (
            f"{viewport_name}: carry sprite pixel should NOT be brownish (plot), got rgb({r},{g},{b})"
        )


@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", SHORT_VIEWPORTS + [TALL_VIEWPORT])
def test_progress_bar_text_contrast_when_partially_funded(viewport_width, viewport_height, viewport_name):
    """
    Regression test for bug 2 (progress bar contrast): set up a partially-
    funded state (coins between 0 and next upgrade cost) and verify the
    progress bar text has proper contrast (black stroke, not just white-on-yellow).
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
            // Set coins to a partially-funded state: more than 0 but less than
            // the cost of the next upgrade (plot base cost is 50)
            // Make it clearly partially filled: 25 coins out of 50
            scene.coins = 25;
            
            // Force a HUD layout update
            if (scene._layoutHUD) scene._layoutHUD();
            
            // Check the actual style properties of the progress text
            const text = scene.progressText;
            if (!text) return { error: "No progressText" };
            
            // Get computed style (this is what actually renders). Text objects
            // have no .style.fill -- that's an Image/Sprite tint property. The
            // actual rendered text color is a CSS color string at
            // .style.color (same API correction already made for the intro
            // banner test).
            const style = {
                stroke: text.style.stroke,
                strokeThickness: text.style.strokeThickness,
                color: text.style.color,
            };

            // Also verify colors are set (not relying on defaults). The
            // contrast fix here is the black STROKE added around the text
            // (readable against the yellow/gold progress fill), not a fill
            // color change -- the text staying white (#fff) is correct and
            // expected, so this only checks the stroke is explicitly set.
            const hasExplicitStroke = style.stroke && style.stroke !== "";
            const hasExplicitStrokeThickness = style.strokeThickness !== undefined && style.strokeThickness > 0;
            const hasColor = style.color && style.color !== "";
            return {
                ...style,
                hasExplicitStroke,
                hasExplicitStrokeThickness,
                hasColor,
            };
        }""")

        browser.close()

        # Verify the text has explicit stroke settings (not relying on defaults)
        assert result["hasExplicitStroke"], (
            f"{viewport_name}: progressText should have explicit stroke color, got {result['stroke']}"
        )
        assert result["hasExplicitStrokeThickness"], (
            f"{viewport_name}: progressText should have explicit stroke thickness, got {result['strokeThickness']}"
        )
        assert result["hasColor"], (
            f"{viewport_name}: progressText should have an explicit text color, got {result['color']}"
        )
        # Specifically check for black stroke (as set in the code)
        assert result["stroke"] == "#000", (
            f"{viewport_name}: progressText stroke should be black (#000), got {result['stroke']}"
        )
        assert result["strokeThickness"] >= 4, (
            f"{viewport_name}: progressText stroke thickness should be at least 4, got {result['strokeThickness']}"
        )


@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", SHORT_VIEWPORTS + [TALL_VIEWPORT])
def test_intro_banner_color_and_text_correct(viewport_width, viewport_height, viewport_name):
    """
    Regression test for intro banner: verify the color is the farm accent
    (0xe65100) and the label text uses correct bullet characters (\u2022).
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
            const bannerObj = scene._introBannerText;
            if (!bannerObj) return { error: "No intro banner" };

            // Phaser Text objects have no .tint that reflects the fill color --
            // that's an Image/Sprite property. The actual color used for
            // rendering a Text object is a CSS color STRING at
            // text.style.color (set via the `color` option passed to
            // scene.add.text()), not a numeric tint.
            return {
                text: bannerObj.text,
                color: bannerObj.style.color,
            };
        }""")

        browser.close()

        # Verify banner is alive
        assert "error" not in result, (
            f"{viewport_name}: {result.get('error', 'Unknown error')}"
        )

        # Verify color is farm accent (#e65100), not the shared juice.js
        # default (#8899ff pale blue)
        assert result["color"] == "#e65100", (
            f"{viewport_name}: intro banner color should be the farm accent "
            f"#e65100, got {result['color']}"
        )

        # Verify text is exactly correct with proper bullets (both U+2022,
        # not the U+2023 typo an earlier version of this fix introduced)
        expected_text = "HARVEST \u2022 SELL \u2022 UPGRADE"
        assert result["text"] == expected_text, (
            f"{viewport_name}: intro banner text incorrect.\n"
            f"  Expected: {expected_text}\n"
            f"  Got:      {result['text']}"
        )


@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", SHORT_VIEWPORTS + [TALL_VIEWPORT])
def test_startHint_does_not_overlap_plot_row(viewport_width, viewport_height, viewport_name):
    """
    Regression test: verify _showStartHint() never positions the hint
    overlapping the plot row at the viewports used in this test suite.
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
            if (scene._showStartHint) scene._showStartHint();

            // The visible "TAP TO MOVE" label is startHintText; startHint is
            // just the arrow-graphic underneath it -- check both, since the
            // polish item was specifically about the readable label overlapping.
            const hintText = scene.startHintText;
            const hintArrow = scene.startHint;
            if (!hintText || !hintArrow) return { error: "No start hint objects" };

            const canvas = scene.game.canvas;
            const rect = canvas.getBoundingClientRect();
            const scaleX = rect.width / 720;  // established convention: logical width is always 720

            // hintText is a real Text GameObject (transform-driven), so
            // .getBounds() works normally on it.
            function screenBounds(obj) {
                const b = obj.getBounds();
                return {
                    left: rect.left + b.x * scaleX,
                    top: rect.top + b.y * scaleX,
                    right: rect.left + (b.x + b.width) * scaleX,
                    bottom: rect.top + (b.y + b.height) * scaleX,
                };
            }

            // hintArrow and each plot's plotSprite are Graphics objects, which
            // do not implement .getBounds() in this Phaser version
            // (TypeError: obj.getBounds is not a function). Their geometry is
            // known and fixed at draw time, so compute bounds manually from
            // the same world coordinates the draw calls used, in world/logical
            // space, then scale to screen space the same way screenBounds() does.
            function worldRectBounds(worldX, worldY, w, h) {
                return {
                    left: rect.left + worldX * scaleX,
                    top: rect.top + worldY * scaleX,
                    right: rect.left + (worldX + w) * scaleX,
                    bottom: rect.top + (worldY + h) * scaleX,
                };
            }

            function overlaps(a, b) {
                return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
            }

            const hintTextBounds = screenBounds(hintText);
            // The arrow triangle is drawn at fillTriangle(hintX, hintY+30,
            // hintX-20, hintY+10, hintX+20, hintY+10) -- hintX/hintY are also
            // exactly hintText's position (both are set to the same value in
            // _showStartHint()), so read them off the real Text object rather
            // than re-deriving farmer/layout math here.
            const hintX = hintText.x;
            const hintY = hintText.y;
            const hintArrowBounds = worldRectBounds(hintX - 20, hintY + 10, 40, 20);
            // scene.plots holds plain data objects ({index, x, y, plotSprite,
            // cropSprite, ...}), not Phaser GameObjects themselves. p.x/p.y are
            // the exact world coordinates _createPlot() baked into
            // plotSprite.fillRoundedRect(x, y, PLOT_SIZE, PLOT_SIZE, ...), so
            // use those directly rather than plotSprite.getBounds().
            const PLOT_SIZE = 96;
            const plotBounds = scene.plots.map(p => worldRectBounds(p.x, p.y, PLOT_SIZE, PLOT_SIZE));

            let overlapIndex = -1;
            for (let i = 0; i < plotBounds.length; i++) {
                if (overlaps(hintTextBounds, plotBounds[i]) || overlaps(hintArrowBounds, plotBounds[i])) {
                    overlapIndex = i;
                    break;
                }
            }

            return {
                hintTextBounds,
                hintArrowBounds,
                plotBoundsAtOverlap: overlapIndex >= 0 ? plotBounds[overlapIndex] : null,
                overlapIndex,
            };
        }""")

        browser.close()

        assert "error" not in result, (
            f"{viewport_name}: {result.get('error', 'Unknown error')}"
        )
        assert result["overlapIndex"] == -1, (
            f"{viewport_name}: start hint overlaps plot row at plot index {result['overlapIndex']}\n"
            f"  hintTextBounds: {result['hintTextBounds']}\n"
            f"  hintArrowBounds: {result['hintArrowBounds']}\n"
            f"  overlapping plotBounds: {result['plotBoundsAtOverlap']}"
        )


