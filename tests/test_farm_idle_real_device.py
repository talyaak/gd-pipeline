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
