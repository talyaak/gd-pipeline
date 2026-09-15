#!/usr/bin/env python3
"""Tests for farm_idle juice/HUD features (Part 2b)."""
import pytest
from pathlib import Path
from playwright.sync_api import sync_playwright

HARNESS_DIR = Path(__file__).parent.parent / "harness"


@pytest.mark.slow
def test_stacking_visual_reflects_carried_count():
    """
    Test that the stacking visual on the farmer actually reflects the
    number of carried crops, and clears on sell.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()

        # Capture console logs
        page.on("console", lambda msg: print(f"BROWSER: {msg.text}"))

        html_path = HARNESS_DIR / "farm_idle.html"
        page.goto(f"file://{html_path.absolute()}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        page.evaluate("() => { window.__GAME__.scene.scenes[0]._begin(); }")
        page.wait_for_timeout(100)

        # Force coins to buy helper
        page.evaluate("() => { window.__GAME__.scene.scenes[0].coins = 500; }")
        page.evaluate("() => { window.__GAME__.scene.scenes[0].coinsText.setText('Coins: 500'); }")
        page.evaluate("() => window.__GAME__.scene.scenes[0]._buyUpgrade('helper')")
        page.wait_for_timeout(500)

        # Drive one accumulation-to-HELPER_MAX_CARRY(3) cycle via helper,
        # harvesting from 3 different plots in turn (a single plot can't be
        # re-harvested until it regrows, so carryCount must build up across
        # distinct plots -- it must NOT be reset to 0 between harvests, that
        # would defeat the whole point of testing accumulation).
        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            const helper = scene.helpers[0];
            let maxStackSize = 0;
            helper.carryCount = 0;

            for (let i = 0; i < 3; i++) {
                const plot = scene.plots[i];
                plot.readyAt = scene.time.now - 1;
                helper.x = plot.x + 30; helper.y = plot.y + 30;
                helper.sprite.x = helper.x; helper.sprite.y = helper.y;
                helper.state = 'seeking_plot';
                // One deterministic tick: seeking_plot finds this plot (dist
                // 0, since the helper is teleported directly onto it) ->
                // moving_to_plot -> harvest, all in the same _updateHelper
                // call since the three state blocks run sequentially.
                scene.update(scene.time.now, 16);
                maxStackSize = Math.max(maxStackSize, scene.carrySprites.length);
                console.log(`Harvest ${i}: carrySprites=${scene.carrySprites.length}, helper.carryCount=${helper.carryCount}, helper.state=${helper.state}`);
            }

            // After 3 harvests, carryCount should have hit HELPER_MAX_CARRY
            // and helper.state should already be 'moving_to_stall'. Teleport
            // to the LIVE computed stall position (scene._computeStallLayout()
            // -- real-device defect #3's single source of truth) rather than
            // a hardcoded (176, 1308): that value only matched the stall's
            // rendered position back when _updateMagnet()/helper-targeting
            // read the separate fixed STALL_Y constant, which is exactly the
            // drift bug defect #3 fixes -- a hardcoded coordinate here would
            // now silently stop landing within MAGNET_RADIUS of the real
            // sell target on most viewports.
            const stall = scene._computeStallLayout();
            helper.x = stall.centerX; helper.y = stall.centerY;
            helper.sprite.x = helper.x; helper.sprite.y = helper.y;
            scene.update(scene.time.now, 16);
            console.log(`After sell attempt: carrySprites=${scene.carrySprites.length}, helper.state=${helper.state}`);

            return { maxStackSize, stackCleared: scene.carrySprites.length === 0, finalStack: scene.carrySprites.length };
        }""")

        browser.close()

        print(f"Max stack size observed: {result['maxStackSize']}")
        print(f"Stack cleared on sell: {result['stackCleared']}")

        # Stack should grow to at least 2 (multiple crops carried at once)
        assert result['maxStackSize'] >= 2, f"Expected stack to grow to at least 2, got max {result['maxStackSize']}"
        # Stack should clear on sell
        assert result['stackCleared'] is True, f"Stack should clear on sell, but had {result['finalStack']} items left"
        # Final stack should be 0
        assert result['finalStack'] == 0, f"Expected final stack to be 0, got {result['finalStack']}"


@pytest.mark.slow
def test_coin_fly_to_counter_completes_and_updates():
    """
    Test that the coin fly-to-counter animation actually completes
    and the counter value updates correctly (not just that a tween is created).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()

        page.on("console", lambda msg: print(f"BROWSER: {msg.text}"))

        html_path = HARNESS_DIR / "farm_idle.html"
        page.goto(f"file://{html_path.absolute()}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        page.evaluate("() => { window.__GAME__.scene.scenes[0]._begin(); }")
        page.wait_for_timeout(100)

        # Force coins to buy helper
        page.evaluate("() => { window.__GAME__.scene.scenes[0].coins = 300; }")
        page.evaluate("() => { window.__GAME__.scene.scenes[0].coinsText.setText('Coins: 300'); }")
        page.evaluate("() => window.__GAME__.scene.scenes[0]._buyUpgrade('helper')")
        page.wait_for_timeout(500)

        initial_coins = page.evaluate("""() => window.__GAME__.scene.scenes[0].coins""")
        print(f"Initial coins: {initial_coins}")

        # Drive one full harvest+sell cycle via helper. HELPER_MAX_CARRY is 3
        # -- the helper only heads to the stall once carryCount reaches that,
        # so force carryCount to MAX-1 before this one harvest so it crosses
        # the threshold immediately, matching this test's "one clean cycle"
        # intent without needing to actually harvest 3 separate plots.
        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            const helper = scene.helpers[0];
            const plot = scene.plots[0];

            helper.carryCount = 2;  // HELPER_MAX_CARRY - 1

            // Ready the plot and place helper on it
            plot.readyAt = scene.time.now - 1;
            helper.x = plot.x + 30; helper.y = plot.y + 30;
            helper.sprite.x = helper.x; helper.sprite.y = helper.y;
            helper.state = 'seeking_plot';

            // One deterministic tick: seeking_plot -> moving_to_plot ->
            // harvest (carryCount 2 -> 3, crosses HELPER_MAX_CARRY) ->
            // state becomes 'moving_to_stall', all in the same tick.
            scene.update(scene.time.now, 16);
            console.log(`After harvest: carrySprites=${scene.carrySprites.length}, helper.carryCount=${helper.carryCount}, helper.state=${helper.state}`);

            // Teleport helper near stall and tick again to sell. Uses the
            // LIVE computed stall position (see the sibling test above for
            // why a hardcoded coordinate is wrong post-defect-#3-fix).
            const stall = scene._computeStallLayout();
            helper.x = stall.centerX; helper.y = stall.centerY;
            helper.sprite.x = helper.x; helper.sprite.y = helper.y;
            scene.update(scene.time.now, 16);

            // Return final state
            return {
                finalCoins: scene.coins,
                carryStackLength: scene.carrySprites.length,
                coinsText: scene.coinsText.text
            };
        }""")

        # Wait for animations to complete
        page.wait_for_timeout(2000)

        final_coins = page.evaluate("""() => {
            return window.__GAME__.scene.scenes[0].coins;
        }""")

        print(f"Initial coins: {initial_coins}")
        print(f"Coins after one cycle (immediate): {result['finalCoins']}")
        print(f"Coins after animations complete: {final_coins}")
        print(f"Carry stack length: {result['carryStackLength']}")
        print(f"Coins text: {result['coinsText']}")

        # Real-device defect #5 fix: a single harvest now bursts
        # HARVEST_BURST_SIZE (3) goods into the carry stack instead of
        # exactly 1 (see harness/farm_idle.game.js), so one harvest-sell
        # cycle nets 3 * CROP_SELL_VALUE(10) = 30, not 10.
        expected_increase = 30
        actual_increase = final_coins - initial_coins
        assert actual_increase == expected_increase, (
            f"Expected coins to increase by {expected_increase}, "
            f"got increase of {actual_increase} (from {initial_coins} to {final_coins})"
        )
        # The coins text should match
        assert int(result['coinsText'].replace('Coins: ', '')) == final_coins, (
            f"Coins text {result['coinsText']} doesn't match final coins {final_coins}"
        )
        # Stack should be empty after sell
        assert result['carryStackLength'] == 0, (
            f"Expected carry stack to be empty after sell, got {result['carryStackLength']}"
        )


@pytest.mark.slow
def test_progress_bar_updates_with_plots():
    """
    Test that the top-center progress bar exists and keeps working (does
    not error/disappear) across a purchase. As of the real-device defect #4
    fix, the bar shows coins-toward-next-upgrade rather than a plot-count
    ratio (see PlayScene._cheapestUpgradeCost() in farm_idle.game.js) --
    this test only checks the bar's existence/wiring survives a purchase,
    not its specific numeric proportion.
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

        # Check progress bar exists and has initial state
        result = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            return {
                hasProgressBar: !!scene.progressBarFill,
                hasProgressBarBg: !!scene.progressBarBg,
                progressBarWidth: scene.progressBarFill ? scene.progressBarFill.width : 0,
                progressBarMaxWidth: scene.progressBarFill ? scene.progressBarFill._maxWidth : 0
            };
        }""")

        assert result['hasProgressBar'] is True, "Progress bar fill should exist"
        assert result['hasProgressBarBg'] is True, "Progress bar background should exist"

        # Buy a plot upgrade and check progress bar updates
        page.evaluate("() => { window.__GAME__.scene.scenes[0].coins = 500; }")
        page.evaluate("() => { window.__GAME__.scene.scenes[0].coinsText.setText('Coins: 500'); }")
        page.evaluate("() => window.__GAME__.scene.scenes[0]._buyUpgrade('plot')")
        page.wait_for_timeout(200)

        result2 = page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            return {
                plotCount: scene.plots.length,
                progressBarWidth: scene.progressBarFill ? scene.progressBarFill.width : 0,
                progressBarMaxWidth: scene.progressBarFill ? scene.progressBarFill._maxWidth : 0
            };
        }""")

        assert result2['plotCount'] >= 6, f"Expected at least 6 plots after upgrade, got {result2['plotCount']}"
        print(f"Progress bar width: {result2['progressBarWidth']}, max: {result2['progressBarMaxWidth']}")
        print(f"Plot count: {result2['plotCount']}")

        browser.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])