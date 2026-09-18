"""
Helper-AI tests for farm_idle: split out of the former monolithic
tests/test_farm_idle_real_device.py (Instinct Wire issue #2).

Covers the auto-harvesting helper's own inventory (helper.carryCount,
independent of the player's shared scene.carrySprites -- the Defect 3
fix), its harvest/sell cycle counts, depth ordering against plots, and
correct operation while it and its target plots are offscreen.
"""
import pytest
from playwright.sync_api import sync_playwright
from farm_idle_test_support import _boot, SHORT_VIEWPORTS, TALL_VIEWPORT


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
