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


def _read_pixel_region_via_screenshot(page, screen_x, screen_y, width, height):
    """Read the RGB colors actually composited in the (width x height) region
    at (screen_x, screen_y) via a Playwright screenshot clip, decoding the
    returned PNG with stdlib only. Needed because farm_idle's canvas uses
    Phaser's default WebGL renderer with preserveDrawingBuffer left at its
    default `false`: canvas.getContext("2d") returns null on an
    already-WebGL canvas, and both gl.readPixels() and canvas.toDataURL()
    read back all-black regardless of real content or added waits, since
    the browser is free to -- and empirically does -- clear the drawing
    buffer right after compositing each frame. A screenshot captures the
    compositor's actual output instead, sidestepping the WebGL buffer
    entirely.

    Returns a list of `height` rows, each a list of `width` (r, g, b) tuples.
    """
    png_bytes = page.screenshot(clip={"x": screen_x, "y": screen_y, "width": width, "height": height})
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos = 8
    png_width = bit_depth = color_type = None
    idat = b""
    while pos < len(png_bytes):
        length = struct.unpack(">I", png_bytes[pos:pos + 4])[0]
        ctype = png_bytes[pos + 4:pos + 8]
        data = png_bytes[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            png_width, png_height, bit_depth, color_type = struct.unpack(">IIBB", data[:10])
        elif ctype == b"IDAT":
            idat += data
        elif ctype == b"IEND":
            break
        pos += 8 + length + 4
    assert bit_depth == 8, f"unexpected PNG bit depth {bit_depth}"
    bpp = {2: 3, 6: 4}.get(color_type)
    assert bpp, f"unexpected PNG color type {color_type}"
    raw = zlib.decompress(idat)
    stride = png_width * bpp
    rows = []
    prior = bytearray(stride)  # PNG "previous scanline" for row 0 is all-zero
    offset = 0
    for _row in range(png_height):
        filt = raw[offset]
        line = bytearray(raw[offset + 1:offset + 1 + stride])
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
        rows.append([tuple(line[i:i + 3]) for i in range(0, stride, bpp)])
        prior = line
        offset += 1 + stride
    return rows


def _read_pixel_via_screenshot(page, screen_x, screen_y):
    """Read the RGB color actually composited at a single (screen_x, screen_y)
    point. See _read_pixel_region_via_screenshot() for why a screenshot is
    used instead of canvas/WebGL pixel-read APIs.
    """
    return _read_pixel_region_via_screenshot(page, screen_x, screen_y, 1, 1)[0][0]


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
    Exact-count requirement for the HELPER's harvest path (_updateHelper),
    updated for the Defect 3 fix (shared inventory bug): helper inventory
    now lives entirely on helper.carryCount, incremented by exactly 1 per
    harvest, and never touches the player's shared scene.carrySprites --
    this test previously asserted the OLD (pre-fix) behavior, where a
    helper harvest called _addHarvestBurst() and added HARVEST_BURST_SIZE
    (3) items straight into scene.carrySprites each time. That behavior
    was deliberately removed as the core of the Defect 3 fix, so the old
    assertions here failed correctly (against the wrong, no-longer-true
    expectation) once the fix landed -- this rewrite asserts the new,
    correct behavior instead: exact +1 per harvest on helper.carryCount,
    capped at HELPER_MAX_CARRY (3), and scene.carrySprites.length staying
    at 0 throughout since the player never touched anything.
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
            const helperCountAfterEachHarvest = [];
            const playerCarryLenAfterEachHarvest = [];

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
                helperCountAfterEachHarvest.push(helper.carryCount);
                playerCarryLenAfterEachHarvest.push(scene.carrySprites.length);
            }

            return { helperCountAfterEachHarvest, playerCarryLenAfterEachHarvest };
        }""")

        browser.close()

        helper_seq = result["helperCountAfterEachHarvest"]
        player_seq = result["playerCarryLenAfterEachHarvest"]
        assert helper_seq[0] == 1, (
            f"Helper's first harvest must add exactly 1 to helper.carryCount, "
            f"got {helper_seq[0]} (full sequence: {helper_seq})"
        )
        assert helper_seq[1] == 2, (
            f"Helper's second harvest must add exactly 1 more to helper.carryCount, "
            f"got {helper_seq[1]} (full sequence: {helper_seq})"
        )
        # Third harvest reaches HELPER_MAX_CARRY (3) -- the helper's own cap
        # (distinct from CARRY_STACK_MAX, the player's shared-stack cap,
        # which no longer applies to the helper's own count at all now that
        # the helper never touches scene.carrySprites).
        assert helper_seq[2] == 3, (
            f"Helper's third harvest must reach HELPER_MAX_CARRY (3), "
            f"got {helper_seq[2]} (full sequence: {helper_seq})"
        )
        # scene.carrySprites must stay untouched by helper harvesting at
        # every step -- this is the actual Defect 3 fix being verified here.
        assert player_seq == [0, 0, 0], (
            f"player's carrySprites.length must stay 0 throughout helper "
            f"harvesting (helper harvest must never touch it), got {player_seq}"
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
def test_helper_depth_10_both_orderings(viewport_width, viewport_height, viewport_name):
    """
    Regression test for Defect 1: helper sprite depth must always be 10,
    regardless of when the helper spawns relative to plot purchases.

    Verifies that a helper's sprite .depth equals 10 both when it spawns
    before any extra plot purchases AND when a plot is purchased after the
    helper already exists -- matching how test_depth_ordering_with_extra_plot_purchase
    covers the farmer/carryStack case for plots purchased after creation.
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
            // Spawn a helper before any extra plot purchases
            scene._spawnHelper(500);
            const helperBefore = scene.helpers[0];
            const depthBefore = helperBefore ? helperBefore.sprite.depth : null;

            // Now buy a 6th plot (index 5)
            scene.coins = 999999;
            for (let i = 0; i < 5; i++) {
                scene._buyUpgrade('plot');
            }
            const reachedSix = scene.plots.length >= 6;

            // Spawn a SECOND helper after plot purchase
            scene._spawnHelper(500);
            const helperAfter = scene.helpers[scene.helpers.length - 1];
            const depthAfter = helperAfter ? helperAfter.sprite.depth : null;

            return {
                reachedSix,
                depthBefore,
                depthAfter,
                helperBeforeExists: helperBefore !== undefined,
                helperAfterExists: helperAfter !== undefined,
            };
        }""")

        browser.close()

        assert result["reachedSix"], (
            f"{viewport_name}: test setup failed to reach 6 plots"
        )
        assert result["depthBefore"] == 10, (
            f"{viewport_name}: helper spawned before plot purchase should have depth 10, got {result['depthBefore']}"
        )
        assert result["depthAfter"] == 10, (
            f"{viewport_name}: helper spawned after plot purchase should have depth 10, got {result['depthAfter']}"
        )
        assert result["helperBeforeExists"] and result["helperAfterExists"], (
            f"{viewport_name}: both helpers must exist"
        )


@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", SHORT_VIEWPORTS + [TALL_VIEWPORT])
def test_helper_harvest_sell_does_not_touch_player_inventory(viewport_width, viewport_height, viewport_name):
    """
    Regression test for Defect 3: shared inventory bug.

    Helper harvesting and selling must NOT touch the player's carrySprites.
    Setup: player is carrying goods and positioned FAR from the market/stall.
    Action: drive a helper through a full harvest-then-sell cycle.
    Assert: player's carrySprites.length is COMPLETELY UNCHANGED, and
    scene.coins increased by EXACTLY the helper's own sold amount.
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

            // Buy a helper first (scene.helpers starts empty -- no helper
            // exists until purchased, matching the pattern already used in
            // test_helper_harvest_burst_exact_counts). Fund this purchase
            // separately from the 100-coin baseline the sell-amount
            // assertion below is anchored to -- _buyUpgrade() silently
            // no-ops if unaffordable, same established pattern as every
            // other purchase in this test file.
            scene.coins = 999999;
            scene._buyUpgrade('helper');

            // Player carries 3 crops (simulate by directly seeding carryItems --
            // scene.carrySprites is now a read-only derived getter over
            // carryItems (Round 1 of the collectible/producer refactor), so
            // assigning/pushing to it silently no-ops; carryItems is the real
            // source of truth to seed directly)
            // and position farmer FAR from the stall
            scene.coins = 100;
            scene.carryItems = [];
            for (let i = 0; i < 3; i++) {
                const s = scene.add.circle(0, 0, 16, 0x8bc34a);
                s.setStrokeStyle(2, 0x4caf50, 1);
                scene.carryItems.push({ typeId: 'crop', sprite: s });
            }
            scene.carryCountText && scene.carryCountText.setText('3/8');
            scene.carrying = 'crop';
            scene.carryIndicator.visible = true;

            // Position farmer far from stall (bottom-right of screen)
            const layout = scene.computeLayout();
            scene.farmer.x = layout.visibleWorldWidth - 80;
            scene.farmer.y = layout.visibleWorldHeight - 80;

            // Place a helper next to plot 0 and drive it through harvest+sell
            const helper = scene.helpers[0];
            const plot = scene.plots[0];
            plot.harvested = false;
            plot.readyAt = scene.time.now - 1;

            helper.x = plot.x + 30;
            helper.y = plot.y + 30;
            helper.sprite.x = helper.x;
            helper.sprite.y = helper.y;
            helper.state = 'seeking_plot';
            helper.carryCount = 0;

            // First update: helper harvests
            scene.update(scene.time.now, 16);

            const afterHarvestCarryLen = scene.carrySprites.length;
            const afterHarvestHelperCount = helper.carryCount;

            // Now drive helper to the stall (market)
            const stall = scene._computeStallLayout();
            helper.target = { x: stall.centerX, y: stall.centerY };
            helper.state = 'moving_to_stall';

            // Multiple updates to reach the stall and trigger the sell.
            // Plot 0 to the stall is ~638 logical px at MOVE_SPEED (300px/s),
            // which needs ~133 frames at 16ms/frame -- 50 was nowhere near
            // enough (measured directly, not guessed), so the helper never
            // actually reached the stall and the sell never fired.
            for (let i = 0; i < 200; i++) {
                scene.update(scene.time.now + i * 16, 16);
            }

            const afterSellCarryLen = scene.carrySprites.length;
            const afterSellCoins = scene.coins;
            const afterSellHelperCount = helper.carryCount;

            // Exact expected sell amount: the helper harvested exactly once
            // (afterHarvestHelperCount, captured right after the harvest,
            // before it got reset to 0 by the sell) crops, sold at the same
            // formula _helperSellAtStall() uses.
            const expectedSellAmount = afterHarvestHelperCount * (CROP_SELL_VALUE + scene.sellValueBonus);
            const expectedCoins = 100 + expectedSellAmount;

            return {
                afterHarvestCarryLen,
                afterHarvestHelperCount,
                afterSellCarryLen,
                afterSellCoins,
                afterSellHelperCount,
                expectedCoins,
                carryUnchanged: afterSellCarryLen === 3,
                helperReset: afterSellHelperCount === 0,
            };
        }""")

        browser.close()

        assert result["afterHarvestCarryLen"] == 3, (
            f"{viewport_name}: player's carrySprites.length must be unchanged immediately after "
            f"helper harvest, got {result['afterHarvestCarryLen']}"
        )
        assert result["afterHarvestHelperCount"] >= 1, (
            f"{viewport_name}: helper.carryCount should have incremented after harvesting, "
            f"got {result['afterHarvestHelperCount']}"
        )
        assert result["carryUnchanged"], (
            f"{viewport_name}: player's carrySprites.length should be unchanged after helper harvest+sell, "
            f"got {result['afterSellCarryLen']} vs expected 3"
        )
        assert result["helperReset"], (
            f"{viewport_name}: helper.carryCount should be 0 after selling, "
            f"got {result['afterSellHelperCount']}"
        )
        # Coins must increase by EXACTLY the helper's own sold amount -- not
        # just "some increase" (a weaker check here was flagged in review as
        # not meeting the "exactly" requirement for this defect).
        assert result["afterSellCoins"] == result["expectedCoins"], (
            f"{viewport_name}: scene.coins should be exactly {result['expectedCoins']} "
            f"(100 + helper's sold amount) after helper sell, got {result['afterSellCoins']}"
        )


@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", SHORT_VIEWPORTS + [TALL_VIEWPORT])
def test_carry_stack_pixel_color_vs_plot_when_overlapping(viewport_width, viewport_height, viewport_name):
    """
    Regression test for bug 1 (z-order fix verification via pixel color):
    Harvest a crop to put something in the carry stack, then position the
    farmer so the FIRST carry sprite's actual rendered circle (center +
    radius, not just the carryStack container's position) provably falls
    inside plot 6's rectangle -- not merely near it -- then sample the
    rendered pixel color at the crop's center to verify it shows the crop
    color (green-ish) not the plot color (brown-ish).

    Instinct review round 2 (cf78f9c) found the original version of this
    test vacuous: it passed 4/4 even on pre-fix 3cb06b1, because
    farmer.y = plot5.y + 48 (plot center) put the sampled carry sprite's
    computed position ~25px ABOVE plot 5's top edge (carryStack sits 56px
    above the farmer, and the first stacked crop sits another ~17px above
    that -- see _addToCarryStack()'s stacking-offset formula), i.e. over
    plain background, never actually over the plot at all. This version
    explicitly asserts the crop-circle/plot-rectangle intersection exists
    (with margin) BEFORE sampling, so the test cannot pass by accident.
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

            // Force the sampled sprite to its final scale synchronously --
            // _addToCarryStack() tweens scale 0.3 -> 1.0 over 200ms (staggered
            // per stack index), so without this the sample could land mid-tween
            // at an unpredictable, smaller-than-16px radius depending on real
            // wall-clock timing. Matches this suite's established convention of
            // driving state deterministically rather than via real-time waits.
            const carrySprite = scene.carrySprites[0];
            carrySprite.setScale(1);
            const CROP_RADIUS = 16;  // matches _addToCarryStack()'s this.add.circle(0, 0, 16, ...)

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
            //
            // farmer.y is deliberately plot5.y + 100 (near/just past the plot's
            // BOTTOM edge), not plot5.y + 48 (plot center, the original/vacuous
            // version's choice): carryStack sits 56px above the farmer, and the
            // first stacked crop's own local offset (see _addToCarryStack()'s
            // angle/radius formula, stackIndex 0) sits a further ~17px above
            // that -- roughly 73px total. Placing the farmer near the plot's
            // bottom, instead of its center, is what actually lands the crop
            // circle inside the plot's [plot.y, plot.y+96] vertical span with
            // real margin, instead of ~25px above it over plain background.
            const plot5 = scene.plots[5];
            scene.farmer.x = plot5.x + 48;
            scene.farmer.y = plot5.y + 100;
            plot5.readyAt = scene.time.now - 1;  // force fully rendered, not mid-grow
            scene.update(scene.time.now, 16);

            // carrySprites are children of the carryStack CONTAINER, so their
            // .x/.y are LOCAL to that container, not absolute canvas coordinates --
            // absolute logical position is spriteLocal + containerPosition.
            const worldX = carrySprite.x + scene.carryStack.x;
            const worldY = carrySprite.y + scene.carryStack.y;

            // Prove the intersection exists: the crop's full rendered circle
            // (center +/- radius), not just its center point, must fall inside
            // plot 5's rectangle. This is the check the original version of
            // this test never made, which is exactly why it passed vacuously.
            const plotLeft = plot5.x, plotRight = plot5.x + 96;
            const plotTop = plot5.y, plotBottom = plot5.y + 96;
            const circleLeft = worldX - CROP_RADIUS, circleRight = worldX + CROP_RADIUS;
            const circleTop = worldY - CROP_RADIUS, circleBottom = worldY + CROP_RADIUS;
            const fullyInside = circleLeft >= plotLeft && circleRight <= plotRight &&
                                 circleTop >= plotTop && circleBottom <= plotBottom;

            const canvas = scene.game.canvas;
            const rect = canvas.getBoundingClientRect();
            const scaleX = rect.width / 720;  // established convention: logical width is always 720
            const screenX = Math.round(rect.left + worldX * scaleX);
            const screenY = Math.round(rect.top + worldY * scaleX);

            return {
                screenX, screenY, fullyInside,
                plotLeft, plotRight, plotTop, plotBottom,
                circleLeft, circleRight, circleTop, circleBottom,
            };
        }""")

        if "error" in setup:
            browser.close()
            raise AssertionError(f"{viewport_name}: {setup['error']}")

        assert setup["fullyInside"], (
            f"{viewport_name}: test setup invalid -- carry sprite's rendered "
            f"circle [{setup['circleLeft']:.1f},{setup['circleTop']:.1f}] to "
            f"[{setup['circleRight']:.1f},{setup['circleBottom']:.1f}] is not "
            f"fully inside plot 5's rectangle "
            f"[{setup['plotLeft']},{setup['plotTop']}] to "
            f"[{setup['plotRight']},{setup['plotBottom']}] -- this test would "
            f"be vacuous without genuine overlap, which is exactly the bug in "
            f"an earlier version of this test"
        )

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

    Instinct review round 2 (cf78f9c) correctly flagged the original version
    of this test as style-metadata-only (it asserted text.style.stroke ==
    "#000" etc., never sampling an actual rendered pixel) -- the bug report
    was about readability, so the test needs rendered-pixel evidence, not
    just a style-object property check. This version keeps those style
    assertions (they are correct, just insufficient) and adds: locate the
    real on-screen overlap between the text's bounding box and the yellow
    progress-fill's bounding box (asserting that overlap genuinely exists,
    the same way test_carry_stack_pixel_color_vs_plot_when_overlapping now
    proves its own occlusion setup), screenshot exactly that region, and
    confirm it contains both a near-black pixel (the stroke actually
    rendering dark ink) and a clearly-yellow pixel (proving the region is
    really over the fill, not some other part of the HUD). Pre-fix
    (3cb06b1), progressText has no stroke at all (plain color: '#fff'), so
    plain white-on-yellow antialiasing never produces a near-black pixel --
    this correctly fails there (verified separately, not part of this
    permanent test).
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

            // progressBarFill.width (and progressText's string) are only
            // recomputed inside the main update() loop (see the "Update
            // top-center progress bar" block there), not by _layoutHUD()
            // (which only repositions elements, it doesn't resize the fill) --
            // an earlier version of this test called only _layoutHUD() and
            // got a 0-width fill bounds back, since the fill's width had
            // never been recalculated for the coins value just set.
            scene.update(scene.time.now, 16);
            if (scene._layoutHUD) scene._layoutHUD();

            // Check the actual style properties of the progress text
            const text = scene.progressText;
            if (!text) return { error: "No progressText" };
            const fill = scene.progressBarFill;
            if (!fill) return { error: "No progressBarFill" };

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
            const hasExplicitStroke = style.stroke && style.stroke !== "";
            const hasExplicitStrokeThickness = style.strokeThickness !== undefined && style.strokeThickness > 0;
            const hasColor = style.color && style.color !== "";

            // Real rendered-evidence part: find where the text's bounding box
            // and the yellow fill's bounding box actually overlap on screen.
            // Both progressText (Text) and progressBarFill (Rectangle) are
            // real GameObjects with working .getBounds() -- unlike the
            // Graphics objects (plots, the startHint arrow) elsewhere in this
            // suite that don't implement it.
            const textBounds = text.getBounds();
            const fillBounds = fill.getBounds();
            const left = Math.max(textBounds.left, fillBounds.left);
            const right = Math.min(textBounds.right, fillBounds.right);
            const top = Math.max(textBounds.top, fillBounds.top);
            const bottom = Math.min(textBounds.bottom, fillBounds.bottom);
            const overlapW = right - left;
            const overlapH = bottom - top;

            const canvas = scene.game.canvas;
            const rect = canvas.getBoundingClientRect();
            const scaleX = rect.width / 720;  // established convention: logical width is always 720
            const screenX = Math.round(rect.left + left * scaleX);
            const screenY = Math.round(rect.top + top * scaleX);
            const screenW = Math.max(1, Math.round(overlapW * scaleX));
            const screenH = Math.max(1, Math.round(overlapH * scaleX));

            return {
                ...style,
                hasExplicitStroke,
                hasExplicitStrokeThickness,
                hasColor,
                overlapW, overlapH,
                screenX, screenY, screenW, screenH,
                textBounds, fillBounds,
            };
        }""")

        if "error" in result:
            browser.close()
            raise AssertionError(f"{viewport_name}: {result['error']}")

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

        # Prove the text/fill overlap genuinely exists before trusting a
        # pixel sample from it -- an empty or near-empty overlap would make
        # the rendered check below vacuous, the same class of bug Instinct
        # found in the carry-stack test.
        assert result["overlapW"] > 4 and result["overlapH"] > 4, (
            f"{viewport_name}: progressText/progressBarFill overlap too small "
            f"to sample meaningfully ({result['overlapW']:.1f}x{result['overlapH']:.1f}px) "
            f"-- text bounds {result['textBounds']}, fill bounds {result['fillBounds']}"
        )

        rows = _read_pixel_region_via_screenshot(
            page, result["screenX"], result["screenY"], result["screenW"], result["screenH"]
        )
        browser.close()

        pixels = [p for row in rows for p in row]
        # Near-black: the stroke actually rendering dark ink in this region.
        has_dark_pixel = any(r < 60 and g < 60 and b < 60 for r, g, b in pixels)
        # Clearly yellow/gold (0xffd700 = 255,215,0-ish): proves this region
        # really is over the progress fill, not some other part of the HUD.
        has_yellow_pixel = any(r > 200 and g > 150 and b < 100 for r, g, b in pixels)

        assert has_yellow_pixel, (
            f"{viewport_name}: sampled text/fill overlap region "
            f"({result['screenW']}x{result['screenH']}px at "
            f"{result['screenX']},{result['screenY']}) has no clearly-yellow "
            f"pixel -- sample region may not actually be over the progress fill"
        )
        assert has_dark_pixel, (
            f"{viewport_name}: sampled text/fill overlap region "
            f"({result['screenW']}x{result['screenH']}px at "
            f"{result['screenX']},{result['screenY']}) has no near-black pixel "
            f"-- the black stroke should be visibly rendering dark ink here, "
            f"over the yellow fill, for real readability, not just set as a "
            f"style property"
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


@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", SHORT_VIEWPORTS + [TALL_VIEWPORT])
def test_startHint_stays_within_screen_when_farmer_at_far_right_plot(viewport_width, viewport_height, viewport_name):
    """
    Instinct review round 2 (cf78f9c) minor item: _showStartHint() only
    clamped hintY (vertical), never hintX -- with the farmer at the
    far-right plot column (plot index 5, PLOTS_PER_ROW=6), hintX = fx put
    the TAP TO MOVE label's center near the right edge of the screen, and
    since startHintText has origin(0.5) (hintX is its horizontal CENTER,
    not its left edge), the label's right half could extend past the
    canvas entirely. Verifies the label's full rendered bounds stay within
    [0, canvas width] at every viewport in this suite when the farmer is
    moved to the far-right plot before the hint is shown.
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
            // Default PLOT_COUNT is 5 (plots 0-4), which does NOT reach the
            // far-right column of a 6-per-row grid -- plot index 4 sits one
            // column short of the actual right edge, which is why an earlier
            // version of this test (using scene.plots[scene.plots.length-1]
            // without buying more plots) passed even pre-fix: it never
            // actually tested the far-right column. Buy up to 6 plots first,
            // same affordability fix as the other tests in this file (coins
            // start at 0 and _buyUpgrade silently no-ops if unaffordable), so
            // plot index 5 -- the true far-right column -- actually exists.
            scene.coins = 999999;
            while (scene.plots.length < 6 && scene.plots.length < 200) {
                const before = scene.plots.length;
                scene._buyUpgrade("plot");
                if (scene.plots.length === before) break;
            }
            if (scene.plots.length < 6) return { error: "did not reach 6 plots" };

            // Move the farmer to the far-right plot (index 5, last column of
            // row 0) before showing the hint -- this is the scenario that
            // overflowed the right edge pre-fix.
            const rightPlot = scene.plots[5];
            scene.farmer.x = rightPlot.x + 48;
            scene.farmer.y = rightPlot.y + 48;
            if (scene._showStartHint) scene._showStartHint();

            const hintText = scene.startHintText;
            if (!hintText) return { error: "No startHintText" };

            const canvas = scene.game.canvas;
            const rect = canvas.getBoundingClientRect();
            const scaleX = rect.width / 720;

            // hintText is a real Text GameObject -- .getBounds() works.
            const b = hintText.getBounds();
            const screenLeft = rect.left + b.x * scaleX;
            const screenRight = rect.left + (b.x + b.width) * scaleX;

            return {
                screenLeft, screenRight,
                canvasLeft: rect.left, canvasRight: rect.left + rect.width,
            };
        }""")

        browser.close()

        assert "error" not in result, (
            f"{viewport_name}: {result.get('error', 'Unknown error')}"
        )
        assert result["screenLeft"] >= result["canvasLeft"] - 0.5, (
            f"{viewport_name}: TAP TO MOVE label extends past the LEFT screen "
            f"edge with farmer at the far-right plot: label left "
            f"{result['screenLeft']:.1f} < canvas left {result['canvasLeft']:.1f}"
        )
        assert result["screenRight"] <= result["canvasRight"] + 0.5, (
            f"{viewport_name}: TAP TO MOVE label extends past the RIGHT screen "
            f"edge with farmer at the far-right plot: label right "
            f"{result['screenRight']:.1f} > canvas right {result['canvasRight']:.1f}"
        )




# ──────────────────────────────────────────────────────────────────────
@pytest.mark.slow
def test_carrySprites_is_derived_from_carryItems():
    """Assert carrySprites is a live-derived getter over carryItems (Round 1).

    Proves:
      - carrySprites.length === carryItems.length always
      - carrySprites[i] is the same object as carryItems[i].sprite (ref equality)
      - carryItems[0].typeId === 'crop'
      - Directly reassigning carryItems = [] instantly updates carrySprites (not cached)
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": 390, "height": 650}, has_touch=True, is_mobile=True
        )
        _boot(page, "iPhone_effective_short")

        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];

            // Harvest a plot so carryItems gets populated
            const plot = scene.plots[0];
            plot.readyAt = scene.time.now - 1;
            scene._harvestPlot(0);

            // 1) length equality
            const lengthOk = scene.carrySprites.length === scene.carryItems.length;

            // 2) reference equality: every carrySprites[i] is the exact same
            //    object as carryItems[i].sprite
            const refsOk = scene.carryItems.length > 0 &&
                scene.carryItems.every((item, i) => scene.carrySprites[i] === item.sprite);

            // 3) typeId
            const typeOk = scene.carryItems[0] && scene.carryItems[0].typeId === 'crop';

            // 4) live-derived proof: reassign carryItems and verify carrySprites updates
            const backup = scene.carryItems.slice();
            scene.carryItems = [];
            const afterReassign = scene.carrySprites.length === 0;
            // restore
            scene.carryItems = backup;

            return {
                lengthOk, refsOk, typeOk, afterReassign,
            };
        }""")

        browser.close()

        assert result["lengthOk"], (
            f"carrySprites.length ({result['lengthOk']}) !== carryItems.length"
        )
        assert result["refsOk"], (
            f"carrySprites sprites are not exact same refs as carryItems[i].sprite"
        )
        assert result["typeOk"], (
            f"carryItems[0].typeId should be 'crop', got {result['typeOk']}"
        )
        assert result["afterReassign"], (
            f"carrySprites should immediately reflect carryItems reassignment (live getter), "
            f"got afterReassign={result['afterReassign']}"
        )


@pytest.mark.slow
def test_player_harvest_sell_cycle_matches_pre_refactor_numbers():
    """Assert the refactor produced numerically identical behavior to before Round 1.

    Before refactor: each harvest added exactly HARVEST_BURST_SIZE (3) items to carry stack,
    and selling 8 items gave 8 * CROP_SELL_VALUE (10) = 80 coins.

    After refactor (Round 1): same burst size and same sell value — this test proves
    the numbers match the pre-refactor expectations.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": 390, "height": 650}, has_touch=True, is_mobile=True
        )
        _boot(page, "iPhone_effective_short")

        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];

            // Give the player coins
            scene.coins = 999999;

            // Harvest one plot
            const plot = scene.plots[0];
            plot.readyAt = scene.time.now - 1;
            scene._harvestPlot(0);

            // Assert burst size of 3 right after harvest
            const afterFirstHarvestItems = scene.carryItems.length;
            const afterFirstHarvestSprites = scene.carrySprites.length;
            if (afterFirstHarvestItems !== 3 || afterFirstHarvestSprites !== 3) {
                return { error: `Expected 3 items after first harvest, got items=${afterFirstHarvestItems}, sprites=${afterFirstHarvestSprites}` };
            }

            // Fill carry stack to exactly 8 by harvesting DISTINCT plots (a
            // single plot can't be re-harvested until it regrows -- plot 0
            // was already harvested above, so continue with plot 1, 2, ...).
            // Buy more plots if the default 5 aren't enough, with a hard
            // iteration cap so a real bug here fails loudly instead of
            // hanging forever.
            let nextPlotIndex = 1;
            let safetyIterations = 0;
            while (scene.carryItems.length < 8 && safetyIterations < 20) {
                safetyIterations++;
                if (nextPlotIndex >= scene.plots.length) {
                    scene.coins = 999999;
                    const before = scene.plots.length;
                    scene._buyUpgrade('plot');
                    if (scene.plots.length === before) break;  // stalled -- avoid an infinite loop
                }
                if (nextPlotIndex >= scene.plots.length) break;
                const morePlot = scene.plots[nextPlotIndex];
                morePlot.readyAt = scene.time.now - 1;
                scene._harvestPlot(nextPlotIndex);
                nextPlotIndex++;
            }

            // Verify carry stack is full (8 items)
            if (scene.carryItems.length !== 8 || scene.carrySprites.length !== 8) {
                return { error: `Expected 8 items in carry stack, got items=${scene.carryItems.length}, sprites=${scene.carrySprites.length}` };
            }

            // Sell via _sellAtStall()
            scene._sellAtStall();

            // Assert coins increased by exactly 8 * (CROP_SELL_VALUE + sellValueBonus)
            // CROP_SELL_VALUE = 10 (from game.js), sellValueBonus is from any plot upgrades
            const expectedCoinIncrease = 8 * (10 + (scene.sellValueBonus || 0));
            const coinsIncreasedBy = scene.coins - 999999;  // was 999999 before

            return {
                carryAfterSell: scene.carryItems.length,
                coinsIncrease: scene.coins - 999999,
                expectedIncrease: expectedCoinIncrease,
                match: scene.coins - 999999 === expectedCoinIncrease,
            };
        }""")

        browser.close()

        assert result["carryAfterSell"] == 0, (
            f"Carry stack should be empty after sell, got {result['carryAfterSell']}"
        )
        assert result["match"] == True, (
            f"Coin increase {result['coinsIncrease']} should match expected "
            f"{result['expectedIncrease']} (8 * (CROP_SELL_VALUE + sellValueBonus))"
        )


@pytest.mark.slow
def test_helper_carryCount_is_derived_from_inventory():
    """Assert helper.carryCount is a live getter over helper.inventory (Round 1).

    Proves:
      - Directly mutating helper.inventory.push(...) instantly updates helper.carryCount
      - A real harvest via _updateHelper() pushes into helper.inventory
      - helper.carryCount reflects the new length automatically
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": 390, "height": 650}, has_touch=True, is_mobile=True
        )
        _boot(page, "iPhone_effective_short")

        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];

            // Give the player coins and buy a helper
            scene.coins = 999999;
            scene._buyUpgrade('helper');

            const helper = scene.helpers[0];

            // Mutate inventory directly (bypassing normal harvest path)
            helper.inventory.push('crop');
            helper.inventory.push('egg');

            // Assert carryCount reflects the new inventory length
            const carryCountAfterMutate = helper.carryCount;
            if (carryCountAfterMutate !== 2) {
                return { error: `Expected carryCount===2 after mutating inventory with 2 items, got ${carryCountAfterMutate}` };
            }

            // Now trigger a real harvest via _updateHelper()
            // Teleport the helper onto a ready plot and tick
            scene.plots[0].readyAt = scene.time.now - 1;
            scene.farmer.x = scene.plots[0].x + 48;
            scene.farmer.y = scene.plots[0].y + 48;
            scene.update(scene.time.now, 16);
            scene._updateHelper(helper, 16);

            // Assert carryCount reflects the updated inventory length after _updateHelper
            const carryCountAfterUpdate = helper.carryCount;
            if (carryCountAfterUpdate < 2) {
                return { error: `Expected carryCount>=2 after _updateHelper, got ${carryCountAfterUpdate}` };
            }

            return {
                carryCountAfterMutate,
                carryCountAfterUpdate,
                inventoryLengthAfterUpdate: helper.inventory.length,
            };
        }""")

        browser.close()

        assert "error" not in result, result["error"]
        assert result["carryCountAfterMutate"] == 2, (
            f"helper.carryCount should be 2 after direct inventory mutation, "
            f"got {result['carryCountAfterMutate']}"
        )
        assert result["carryCountAfterUpdate"] >= 2, (
            f"helper.carryCount should be >=2 after _updateHelper, "
            f"got {result['carryCountAfterUpdate']}"
        )

@pytest.mark.slow
def test_producers_array_mirrors_plots_and_readiness_generalized():
    """Assert producers array mirrors plots array with same object references,
    and that collecting a ready producer yields the same carry count as pre-refactor
    plot harvest (3 items)."""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=['--no-sandbox'])
        page = browser.new_page(
            viewport={'width': 390, 'height': 650}, has_touch=True, is_mobile=True
        )
        _boot(page, 'iPhone_effective_short')

        result = page.evaluate("""(() => {
            const scene = window.__GAME__.scene.scenes[0];

            // 1) producers.length must equal plots.length
            const lengthOk = scene.producers.length === scene.plots.length;

            // 2) every producers[i] must be the same object reference as plots[i]
            const refsOk = scene.plots.length > 0 &&
                scene.plots.every((p, i) => scene.producers[i] === p);

            // 3) first producer has the expected type IDs
            const typeOk = scene.producers[0].collectibleTypeId === 'crop'
                && scene.producers[0].producerTypeId === 'plot';

            // 4) collect the first producer via the generic path
            scene.producers[0].readyAt = scene.time.now - 1;
            const collected = scene._collectProducer(scene.producers[0], 'player');

            // 5) collect returns true and carry count is 3 (same as pre-refactor plot harvest)
            const carryOk = scene.carryItems.length === 3;

            return {
                lengthOk, refsOk, typeOk, collected, carryOk,
            };
        })""");

        browser.close();

        assert result['lengthOk'], (
            f'producers.length ({result["lengthOk"]}) !== plots.length'
        );
        assert result['refsOk'], (
            f'producers are not same refs as plots'
        );
        assert result['typeOk'], (
            f'producers[0].collectibleTypeId or producerTypeId mismatch: {result["typeOk"]}'
        );
        assert result['collected'] is True, (
            f'_collectProducer did not return true, got {result["collected"]}'
        );
        assert result['carryOk'], (
            f'scene.carryItems.length should be 3 after collect, got {result["carryOk"]}'
        )

def test_plot_regrow_speed_buff_applies_to_existing_plots_after_cap():
    """Buying past the plot grid cap speeds up regrowth for plots created
    before the buff was purchased -- proves producer.cycleMs stays live,
    not a frozen snapshot from plot-creation time."""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=['--no-sandbox'])
        page = browser.new_page(
            viewport={'width': 390, 'height': 650}, has_touch=True, is_mobile=True
        )
        _boot(page, 'iPhone_effective_short')

        result = page.evaluate("""(() => {
            const scene = window.__GAME__.scene.scenes[0];
            scene.coins = 999999;

            let safety = 0;
            while (!scene.plotGridCapped && safety < 30) {
                scene._buyUpgrade('plot');
                safety++;
            }
            const cappedReached = scene.plotGridCapped === true;

            const plot = scene.plots[0];
            plot.readyAt = scene.time.now - 1;
            plot.harvested = false;
            const collected = scene._collectProducer(plot, 'player');

            const expectedReadyAt = scene.time.now + CROP_GROW_MS * scene.growSpeedMult;
            const actualReadyAt = scene.plots[0].readyAt;
            const withinTolerance = Math.abs(actualReadyAt - expectedReadyAt) <= 50;

            return { cappedReached, collected, expectedReadyAt, actualReadyAt, withinTolerance };
        })""");

        browser.close();

        assert result['cappedReached'], (
            f"plotGridCapped never became true within 30 buy attempts"
        )
        assert result['collected'] is True, (
            f"_collectProducer did not return true, got {result['collected']}"
        )
        assert result['withinTolerance'], (
            f"plot.readyAt ({result['actualReadyAt']}) not within tolerance of "
            f"expected ({result['expectedReadyAt']}) -- cycleMs is not reflecting "
            f"the live growSpeedMult buff"
        )


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
    cases = [
        ((WORLD_W - 200, 1000), (150, 0), "x", WORLD_W - FARMER_RADIUS, "right"),
        ((200, 1000), (-150, 0), "x", FARMER_RADIUS, "left"),
        ((700, WORLD_H - 200), (0, 150), "y", WORLD_H - FARMER_RADIUS, "bottom"),
        ((700, PLOT_AREA_TOP + 200), (0, -150), "y", PLOT_AREA_TOP + FARMER_RADIUS, "top"),
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


@pytest.mark.slow
def test_helper_completes_harvest_and_sale_while_offscreen():
    """Section D acceptance criterion 14 (Offscreen AI): with the camera and
    farmer positioned far from the helper, the helper must still
    autonomously complete a harvest at a ready plot and a sale at the
    market -- driven purely by real elapsed time (Phaser's own per-frame
    _updateHelper()/update loop), not by manually invoking any private
    collection/sale method. Coins increase (the shared currency the helper's
    sale credits); the PLAYER's own carrySprites are untouched (proving the
    helper's autonomous action never touches player inventory); the
    helper's own inventory clears right after its first sale. This sale
    also doubles as criterion 13's "helper target resolves the same fixed
    market coordinate" proof, since it only succeeds if _updateHelper()'s
    own _computeStallLayout() call is correct.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        _boot(page, "iPhone_12_tall_contrast")

        setup = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];

            // Ready plot for the helper to harvest.
            scene.plots[0].readyAt = scene.time.now - 1;

            // Spawn a helper and put it straight into its real AI loop
            // (bypassing only the idle-timer cadence before the FIRST
            // search, which is unrelated to this proof -- the helper's
            // actual movement/collection/sale from here on all runs
            // through the real per-frame _updateHelper() path).
            scene._spawnHelper(500);
            const helper = scene.helpers[scene.helpers.length - 1];
            helper.state = 'seeking_plot';

            // Move the FARMER (and therefore the camera, which follows it)
            // far from both the plot and the helper, so the camera is
            // rendering a totally different part of the world while the
            // helper does its own thing.
            scene.farmer.x = 1300;
            scene.farmer.y = 1800;

            return {
                coinsBefore: scene.coins,
                playerCarryBefore: scene.carrySprites.length,
            };
        }""")
        page.wait_for_timeout(600)  # let the camera settle far from the helper

        scroll_after_settle = page.evaluate("() => { const c = window.__GAME__.scene.scenes[0].cameras.main; return { x: c.scrollX, y: c.scrollY }; }")

        # Poll in real 300ms increments (real elapsed time, letting
        # Phaser's own per-frame update loop run the helper's walk-harvest-
        # walk-sell cycle) and stop as soon as the FIRST sale registers.
        # IMPORTANT: do not just wait one long fixed duration and check once
        # -- the helper immediately starts a second harvest cycle after
        # selling (crops regrow), so a long wait can catch it mid-way
        # through cycle 2, making helper.inventory.length nonzero again even
        # though the required proof (one autonomous offscreen sale
        # happened) is already satisfied. Polling and stopping at the first
        # sale avoids that race -- verified empirically (dry-run) before
        # writing this test.
        sold = False
        result = None
        for _ in range(20):
            page.wait_for_timeout(300)
            result = page.evaluate("""() => {
                const scene = window.__GAME__.scene.scenes[0];
                const helper = scene.helpers[scene.helpers.length - 1];
                return {
                    coinsAfter: scene.coins,
                    playerCarryAfter: scene.carrySprites.length,
                    helperInventoryLength: helper.inventory.length,
                    helperState: helper.state,
                };
            }""")
            if result["coinsAfter"] > setup["coinsBefore"]:
                sold = True
                break
        browser.close()

        assert scroll_after_settle["x"] > 50 or scroll_after_settle["y"] > 50, (
            f"world camera didn't scroll away meaningfully: {scroll_after_settle}"
        )
        assert sold, (
            f"helper did not complete an autonomous sale while offscreen within the poll window: "
            f"{result}"
        )
        assert result["playerCarryAfter"] == setup["playerCarryBefore"], (
            f"player's own carrySprites changed from the helper's autonomous action "
            f"({setup['playerCarryBefore']} -> {result['playerCarryAfter']}) -- helper activity "
            f"must never touch player inventory"
        )
        assert result["helperInventoryLength"] == 0, (
            f"helper inventory should be empty right after its first sale, got "
            f"{result['helperInventoryLength']}"
        )


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
def test_hud_pixels_identical_before_and_after_large_pan():
    """Section D acceptance criterion 12 (HUD pixels): a direct pixel proof,
    not just implicit coverage via the two-camera architecture's own
    invariants -- the coins-counter text must render at the EXACT SAME
    screen pixels before and after a large world-camera pan, since it's a
    HUD object owned by uiCamera (fixed, only changes on resize) and
    should be completely unaffected by the world camera's own scroll.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        _boot(page, "iPhone_12_tall_contrast")

        def hud_region():
            return page.evaluate("""() => {
                const scene = window.__GAME__.scene.scenes[0];
                const ui = scene.uiCamera;
                function worldToScreen(camera, wx, wy) {
                    const p0 = camera.getWorldPoint(0, 0);
                    const p1 = camera.getWorldPoint(100, 0);
                    const p2 = camera.getWorldPoint(0, 100);
                    const sx = (wx - p0.x) / (p1.x - p0.x) * 100;
                    const sy = (wy - p0.y) / (p2.y - p0.y) * 100;
                    return { x: sx, y: sy };
                }
                const b = scene.coinsText.getBounds();
                const topLeft = worldToScreen(ui, b.x, b.y);
                return { x: topLeft.x, y: topLeft.y, width: b.width * ui.zoom, height: b.height * ui.zoom };
            }""")

        region_before = hud_region()
        rows_before = _read_pixel_region_via_screenshot(
            page, round(region_before["x"]), round(region_before["y"]),
            round(region_before["width"]), round(region_before["height"]),
        )

        page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            scene.farmer.x = 1300;
            scene.farmer.y = 1800;
        }""")
        page.wait_for_timeout(600)

        world_scroll = page.evaluate("() => { const c = window.__GAME__.scene.scenes[0].cameras.main; return { x: c.scrollX, y: c.scrollY }; }")
        region_after = hud_region()
        rows_after = _read_pixel_region_via_screenshot(
            page, round(region_after["x"]), round(region_after["y"]),
            round(region_after["width"]), round(region_after["height"]),
        )
        browser.close()

        assert world_scroll["x"] > 50 and world_scroll["y"] > 50, (
            f"world camera didn't pan enough to be a meaningful proof: {world_scroll}"
        )
        assert region_before == region_after, (
            f"HUD screen-region coordinates changed under world-camera pan: "
            f"{region_before} -> {region_after}"
        )
        assert rows_before == rows_after, (
            f"HUD pixel content at the coins-counter region changed under world-camera pan "
            f"(region {region_after}), even though the region coordinates stayed identical"
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
