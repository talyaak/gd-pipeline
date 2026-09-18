"""
HUD/visual-layout pixel tests for farm_idle: split out of the former
monolithic tests/test_farm_idle_real_device.py (Instinct Wire issue #2).

Covers on-screen layout and rendering correctness: no element overlap
across real short-viewport sizes, buy-button affordability contrast,
depth ordering, progress-bar/intro-banner/start-hint contrast and
placement, and HUD pixel stability (the coins counter specifically) across
a large camera pan.
"""
import pytest
from playwright.sync_api import sync_playwright
from farm_idle_test_support import _boot, SHORT_VIEWPORTS, TALL_VIEWPORT, _read_pixel_region_via_screenshot, _read_pixel_via_screenshot


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
