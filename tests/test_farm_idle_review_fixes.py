#!/usr/bin/env python3
"""Tests for farm_idle review blockers fixes."""
import pytest
import time
from pathlib import Path
from playwright.sync_api import sync_playwright


HARNESS_DIR = Path(__file__).parent.parent / "harness"


@pytest.mark.slow
def test_plot_row_wrapping_on_canvas():
    """
    Bug 1: Plots should wrap into rows and stay on-canvas after 6+ purchases.
    
    Asserts: every plot satisfies x >= 0 && x + PLOT_SIZE <= W && y >= 0 && y + PLOT_SIZE < STALL_Y
    after at least 6 purchases (7+ total plots).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()
        
        html_path = HARNESS_DIR / "farm_idle.html"
        page.goto(f"file://{html_path.absolute()}")
        page.wait_for_load_state("networkidle")
        
        # Wait for game to initialize
        page.wait_for_timeout(1000)
        
        # Ensure game is in PLAYING state
        page.evaluate("() => { window.__GAME__.scene.scenes[0]._begin(); }")
        page.wait_for_timeout(100)
        
        # Force enough coins to buy plot upgrade 6+ times
        # Initial PLOT_UPGRADE_BASE_COST=50, PLOT_UPGRADE_COST_GROWTH=150% (1.5x)
        # We need: 50 + 75 + 112 + 168 + 252 + 378 = ~1035 coins for 6 purchases
        page.evaluate("() => { window.__GAME__.scene.scenes[0].coins = 2000; }")
        page.evaluate("() => { window.__GAME__.scene.scenes[0].coinsText.setText('Coins: 2000'); }")
        
        # Buy "More Crop Plots" upgrade 6 times
        for i in range(6):
            page.evaluate("() => window.__GAME__.scene.scenes[0]._buyUpgrade('plot')")
            page.wait_for_timeout(100)  # small delay for UI to update
        
        # Read back all plot positions
        plots_data = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            return scene.plots.map(p => ({ x: p.x, y: p.y, index: p.index }));
        }""")
        
        # Constants from the game
        W = 450
        PLOT_SIZE = 60
        STALL_Y = 700
        
        print(f"Total plots after 6 purchases: {len(plots_data)}")
        for p in plots_data:
            print(f"  Plot {p['index']}: x={p['x']}, y={p['y']}")
        
        # Assert all plots are fully on-canvas and above stall
        for p in plots_data:
            assert p['x'] >= 0, f"Plot {p['index']} x={p['x']} < 0 (off-canvas left)"
            assert p['x'] + PLOT_SIZE <= W, f"Plot {p['index']} x+size={p['x'] + PLOT_SIZE} > W={W} (off-canvas right)"
            assert p['y'] >= 0, f"Plot {p['index']} y={p['y']} < 0 (off-canvas top)"
            assert p['y'] + PLOT_SIZE < STALL_Y, f"Plot {p['index']} y+size={p['y'] + PLOT_SIZE} >= STALL_Y={STALL_Y} (overlaps stall)"
        
        # Should have at least 7 plots (5 initial + 6 purchases = 11)
        assert len(plots_data) >= 7, f"Expected at least 7 plots, got {len(plots_data)}"
        
        browser.close()


@pytest.mark.slow
def test_tween_leak_bounded():
    """
    Bug 2: Tween count should stay bounded over real elapsed time (no infinite tween creation per frame).
    
    Lets the game run idle for 10+ seconds via page.wait_for_timeout, then reads
    window.__GAME__.scene.scenes[0].tweens.getTweens().length and asserts it stays under 50.
    The buggy version would produce many hundreds within 10 seconds at 60fps.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()
        
        html_path = HARNESS_DIR / "farm_idle.html"
        page.goto(f"file://{html_path.absolute()}")
        page.wait_for_load_state("networkidle")
        
        # Wait for game to initialize
        page.wait_for_timeout(1000)
        
        # Ensure game is in PLAYING state
        page.evaluate("() => { window.__GAME__.scene.scenes[0]._begin(); }")
        page.wait_for_timeout(100)
        
        # Force some coins and buy a helper so crops get harvested and regrow
        page.evaluate("() => { window.__GAME__.scene.scenes[0].coins = 1000; }")
        page.evaluate("() => { window.__GAME__.scene.scenes[0].coinsText.setText('Coins: 1000'); }")
        page.evaluate("() => window.__GAME__.scene.scenes[0]._buyUpgrade('helper')")
        page.wait_for_timeout(500)
        
        # Run idle for 10 real seconds - let the auto-assist harvest and regrow crops
        page.wait_for_timeout(10000)
        
        # Read tween count
        tween_count = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            return scene.tweens.getTweens().length;
        }""")
        
        print(f"Active tween count after 10s idle: {tween_count}")
        
        # Fixed version should have ~5-10 tweens (one pulse per ready plot + short-lived juice tweens)
        # Buggy version would have hundreds
        assert tween_count < 50, f"Tween leak detected: {tween_count} active tweens (expected < 50)"
        
        browser.close()


@pytest.mark.slow
def test_crop_regrow_multi_cycle():
    """
    Bug 3 (2nd review round): _harvestPlot set harvested=true and pushed readyAt
    forward, but nothing ever reset harvested to false, so each plot could be
    harvested exactly once and then died forever.

    Deterministic (no reliance on real wall-clock timing, per the standing rule
    that timing-based CI assertions must not be the only proof): forces
    plot.readyAt into the past and calls scene.update() directly to drive one
    frame tick, then re-harvests, repeated across 3 cycles.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()

        html_path = HARNESS_DIR / "farm_idle.html"
        page.goto(f"file://{html_path.absolute()}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        page.evaluate("() => { window.__GAME__.scene.scenes[0]._begin(); }")
        page.wait_for_timeout(100)

        harvest_count = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            const plot = scene.plots[0];
            let harvests = 0;
            for (let cycle = 0; cycle < 3; cycle++) {
                plot.readyAt = scene.time.now - 1;   // force ready
                scene.update(scene.time.now, 16);    // one deterministic frame: regrow-reset runs here
                scene.carrying = null;                // not carrying anything going into this harvest attempt
                scene._harvestPlot(0);
                // _harvestPlot only sets carrying='crop' on an ACTUAL successful
                // harvest -- it early-returns (leaving carrying untouched) when
                // plot.harvested is stuck true, which is exactly the bug this
                // test exists to catch. Checking plot.harvested itself here would
                // be a false-pass trap: it stays true regardless of whether the
                // reset happened, since _harvestPlot's own early-return never
                // flips it back.
                if (scene.carrying === 'crop') harvests++;
                scene.carryIndicator.setVisible(false);
            }
            return harvests;
        }""")

        assert harvest_count == 3, (
            f"Expected plot 0 to be harvestable on all 3 forced cycles, got {harvest_count} "
            f"successful harvests (regrow-reset regression)"
        )

        browser.close()


@pytest.mark.slow
def test_tween_leak_bounded_across_helper_regrow_cycles():
    """
    Updated bounded-tween proof: the round-1 version of this test passed partly
    because plots died after one harvest (the round-2 regrow bug), so it never
    actually exercised more than a handful of harvest events. This version
    drives many real harvest+regrow cycles through the HELPER code path
    specifically (the auto-harvest branch has its own pulseTween stop/null,
    a separate call site from the manual _harvestPlot one) and asserts the
    tween count stays bounded across all of them.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()

        html_path = HARNESS_DIR / "farm_idle.html"
        page.goto(f"file://{html_path.absolute()}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        page.evaluate("() => { window.__GAME__.scene.scenes[0]._begin(); }")
        page.wait_for_timeout(100)

        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            scene.coins = 1000;
            scene._buyUpgrade('helper');
            const helper = scene.helpers[0];
            const plot = scene.plots[0];
            let harvestCycles = 0;

            for (let cycle = 0; cycle < 15; cycle++) {
                // Ready the plot and place the helper exactly on it so the
                // harvest happens within this same update() tick.
                plot.readyAt = scene.time.now - 1;
                helper.x = plot.x + 30; helper.y = plot.y + 30;
                helper.sprite.x = helper.x; helper.sprite.y = helper.y;
                helper.state = 'seeking_plot';
                scene.update(scene.time.now, 16);
                if (plot.harvested) harvestCycles++;

                // Teleport the helper to the stall and tick again to sell,
                // which frees it to seek again next cycle.
                helper.x = 110; helper.y = 735;  // STALL_X + STALL_W/2, STALL_Y + STALL_H/2
                helper.sprite.x = helper.x; helper.sprite.y = helper.y;
                scene.update(scene.time.now, 16);
            }

            // Count only infinite/looping tweens (repeat === -1): those are the
            // actual leak risk (the crop pulse). Calling scene.update() directly
            // drives our game logic but bypasses Phaser's own engine loop, so
            // finite one-shot tweens (e.g. the sell-particle bursts) never get a
            // real frame to self-complete and purge from getTweens() -- counting
            // those would produce a false failure unrelated to the pulse-tween bug.
            const infiniteTweens = scene.tweens.getTweens().filter(t => t.repeat === -1);
            return { harvestCycles, infiniteTweenCount: infiniteTweens.length };
        }""")

        print(f"Helper-driven harvest cycles: {result['harvestCycles']}, infinite tween count: {result['infiniteTweenCount']}")

        assert result['harvestCycles'] >= 10, (
            f"Expected at least 10 successful helper-driven harvest cycles, got {result['harvestCycles']}"
        )
        # At most one infinite pulse tween should exist per plot (5 plots total);
        # the leaked-tween bug created a fresh one every single frame.
        assert result['infiniteTweenCount'] <= 5, (
            f"Infinite tween leak detected after {result['harvestCycles']} helper harvest cycles: "
            f"{result['infiniteTweenCount']} looping tweens active (expected <= 5, one per plot)"
        )

        browser.close()


@pytest.mark.slow
def test_plot_grid_caps_and_redirects_to_buffs():
    """
    Bounded-grid + buff-redirect design (2nd review round): once the plot grid
    reaches MAX_PLOTS (18 = 3 rows x 6/row), further "More Plots" purchases
    must stop spawning plots and instead apply sellValueBonus / growSpeedMult
    buffs, keeping the idle-number-goes-up fantasy without unbounded entities.

    Also re-proves the layout claim precisely: Tal's prior finding was that
    "row 4 lands inside the upgrade panel" when the original spec assumed 8
    rows of headroom fit above it. This asserts every plot's bottom edge
    clears UPGRADE_PANEL_TOP (420), not merely "somewhere on the 450x800
    canvas" which the row-wrapping fix alone would not guarantee.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()

        html_path = HARNESS_DIR / "farm_idle.html"
        page.goto(f"file://{html_path.absolute()}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        page.evaluate("() => { window.__GAME__.scene.scenes[0]._begin(); }")
        page.wait_for_timeout(100)

        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            for (let i = 0; i < 20; i++) {
                scene.coins = 999999999;  // guarantee affordability regardless of exponential cost growth
                scene._buyUpgrade('plot');
            }
            return {
                plotCount: scene.plots.length,
                sellValueBonus: scene.sellValueBonus,
                growSpeedMult: scene.growSpeedMult,
                plotGridCapped: scene.plotGridCapped,
                plots: scene.plots.map(p => ({ x: p.x, y: p.y }))
            };
        }""")

        MAX_PLOTS = 18
        PLOT_SIZE = 60
        UPGRADE_PANEL_TOP = 420
        STALL_Y = 700
        W = 450

        assert result['plotCount'] == MAX_PLOTS, (
            f"Expected the grid to cap at {MAX_PLOTS} plots after 20 purchases, got {result['plotCount']}"
        )
        assert result['plotGridCapped'] is True, "Expected plotGridCapped flag to be set once the cap is hit"
        assert result['sellValueBonus'] > 0, "Expected sellValueBonus buff to apply for purchases past the cap"
        assert 0 < result['growSpeedMult'] < 1, (
            f"Expected growSpeedMult buff to apply for purchases past the cap, got {result['growSpeedMult']}"
        )

        for p in result['plots']:
            assert p['x'] >= 0 and p['x'] + PLOT_SIZE <= W, f"Plot off-canvas horizontally: {p}"
            assert p['y'] >= 0, f"Plot off-canvas above: {p}"
            assert p['y'] + PLOT_SIZE <= UPGRADE_PANEL_TOP, (
                f"Plot bottom edge {p['y'] + PLOT_SIZE} overlaps the upgrade panel "
                f"(top={UPGRADE_PANEL_TOP}): {p}"
            )
            assert p['y'] + PLOT_SIZE < STALL_Y, f"Plot overlaps the stall: {p}"

        browser.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])