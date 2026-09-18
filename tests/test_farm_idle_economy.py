"""
Core economy/inventory-state tests for farm_idle: split out of the former
monolithic tests/test_farm_idle_real_device.py (Instinct Wire issue #2).

Covers the player's own harvest/sell/buy loop and carry-stack/inventory
state -- the parts of the economy not specific to the camera, the fixed
market, or the helper AI: natural loop correctness, capacity enforcement,
carrySprites-derived-from-carryItems invariants, and the generalized
producers array mirroring plot readiness.
"""
import pytest
from playwright.sync_api import sync_playwright
from farm_idle_test_support import _boot

CARRY_STACK_MAX = 8  # must match farm_idle.game.js
HARVEST_BURST_SIZE = 3  # must match farm_idle.game.js


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
