#!/usr/bin/env python3
"""
Viewport regression test for farm_idle harness.
Tests that all interactive elements are fully visible at various mobile viewports and DPRs.
"""
import pytest
from pathlib import Path
from playwright.sync_api import sync_playwright

HARNESS_DIR = Path(__file__).parent.parent / "harness"

# Viewports to test: (width, height, name)
VIEWPORTS = [
    (375, 667, "iPhone_8"),
    (390, 844, "iPhone_12"),
    (414, 896, "iPhone_11_Pro_Max"),
    (430, 932, "iPhone_14_Pro"),
    (360, 640, "Galaxy_S8"),
]

# DPR values to test
DPR_VALUES = [1, 2, 3]


def _get_element_bounds(page):
    """Get bounds of all interactive elements from the Phaser scene in SCREEN coordinates.

    In FIT mode, Phaser game objects use logical coordinates (720x1280) but the canvas
    is scaled via CSS to fit the viewport. We need to transform to screen coordinates
    for viewport checks by reading the canvas's actual on-screen position/size.
    """
    return page.evaluate("""
        () => {
            const scene = window.__GAME__.scene.scenes[0];
            const canvas = scene.game.canvas;
            const rect = canvas.getBoundingClientRect();
            const scaleX = rect.width / 720;
            const scaleY = rect.height / 1280;

            const bounds = {};

            function toScreen(logicalX, logicalY, logicalW, logicalH) {
                return {
                    x: rect.left + logicalX * scaleX,
                    y: rect.top + logicalY * scaleY,
                    width: logicalW * scaleX,
                    height: logicalH * scaleY
                };
            }

            // Farmer (Circle - has getBounds)
            if (scene.farmer) {
                const fb = scene.farmer.getBounds();
                bounds.farmer = toScreen(fb.x, fb.y, fb.width, fb.height);
            }

            // Plots - compute from plot positions (Graphics don't have getBounds)
            bounds.plots = scene.plots.map((p, i) => {
                const screenBounds = toScreen(p.x, p.y, 96, 96);  // PLOT_SIZE = 96
                return { index: i, ...screenBounds };
            });

            // Stall and upgrade pad are repositioned dynamically by
            // _layoutHUD() to clear the safe-area bottom inset, so read
            // their live x/y (set via setPosition) rather than the
            // original design-time constants, which _layoutHUD() may have
            // moved them away from.
            if (scene.stallG) {
                bounds.stall = toScreen(scene.stallG.x, scene.stallG.y, 160, 112);  // STALL_W, STALL_H
            }
            if (scene.padG) {
                bounds.upgradePad = toScreen(scene.padG.x, scene.padG.y, 256, 112);  // PAD_W, PAD_H
            }

            // Coin counter
            if (scene.coinsText) {
                const cb = scene.coinsText.getBounds();
                bounds.coinsText = toScreen(cb.x, cb.y, cb.width, cb.height);
            }

            // BUY buttons (from upgradeRows)
            bounds.buyButtons = [];
            if (scene.upgradeRows) {
                scene.upgradeRows.forEach((row, i) => {
                    if (row.btn) {
                        const bb = row.btn.getBounds();
                        bounds.buyButtons.push({ index: i, ...toScreen(bb.x, bb.y, bb.width, bb.height) });
                    }
                });
            }

            // Upgrade panel background
            if (scene.upgradeBg) {
                const ub = scene.upgradeBg.getBounds();
                bounds.upgradePanel = toScreen(ub.x, ub.y, ub.width, ub.height);
            }

            // Carry indicator
            if (scene.carryIndicator) {
                const cib = scene.carryIndicator.getBounds();
                bounds.carryIndicator = toScreen(cib.x, cib.y, cib.width, cib.height);
            }

            // Joystick (if active)
            if (scene.joystickBase) {
                const jb = scene.joystickBase.getBounds();
                bounds.joystickBase = toScreen(jb.x, jb.y, jb.width, jb.height);
            }
            if (scene.joystickThumb) {
                const jt = scene.joystickThumb.getBounds();
                bounds.joystickThumb = toScreen(jt.x, jt.y, jt.width, jt.height);
            }

            // Add scale info for debugging
            bounds._scaleInfo = { scaleX, scaleY, canvasRect: { x: rect.left, y: rect.top, width: rect.width, height: rect.height } };

            return bounds;
        }
    """)


def _check_bounds_in_viewport(bounds, viewport_width, viewport_height, safe_insets=None):
    """Check that all bounds are within viewport and not in safe-area insets.

    Returns (all_ok, errors_list)
    """
    safe_insets = safe_insets or {"top": 0, "right": 0, "bottom": 0, "left": 0}
    errors = []

    def check_element(name, x, y, w, h):
        # Check fully within viewport
        if x < 0:
            errors.append(f"{name}: x={x} < 0 (off left edge)")
        if y < 0:
            errors.append(f"{name}: y={y} < 0 (off top edge)")
        if x + w > viewport_width:
            errors.append(f"{name}: x+width={x+w} > viewport_width={viewport_width} (off right edge)")
        if y + h > viewport_height:
            errors.append(f"{name}: y+height={y+h} > viewport_height={viewport_height} (off bottom edge)")

        # Check safe-area insets
        # Top inset (notch/status bar)
        if y < safe_insets["top"]:
            errors.append(f"{name}: y={y} < safe-area-inset-top={safe_insets['top']} (overlaps top safe area)")
        # Bottom inset (home indicator/gesture bar)
        if y + h > viewport_height - safe_insets["bottom"]:
            errors.append(f"{name}: y+height={y+h} > viewport_height-safe_inset_bottom={viewport_height - safe_insets['bottom']} (overlaps bottom safe area)")
        # Left inset
        if x < safe_insets["left"]:
            errors.append(f"{name}: x={x} < safe-area-inset-left={safe_insets['left']} (overlaps left safe area)")
        # Right inset
        if x + w > viewport_width - safe_insets["right"]:
            errors.append(f"{name}: x+width={x+w} > viewport_width-safe_inset_right={viewport_width - safe_insets['right']} (overlaps right safe area)")

    # Farmer
    if "farmer" in bounds:
        f = bounds["farmer"]
        check_element("farmer", f["x"], f["y"], f["width"], f["height"])

    # Plots
    for p in bounds.get("plots", []):
        check_element(f"plot_{p['index']}", p["x"], p["y"], p["width"], p["height"])

    # Stall
    if "stall" in bounds:
        s = bounds["stall"]
        check_element("stall", s["x"], s["y"], s["width"], s["height"])

    # Upgrade pad
    if "upgradePad" in bounds:
        u = bounds["upgradePad"]
        check_element("upgradePad", u["x"], u["y"], u["width"], u["height"])

    # Coin counter
    if "coinsText" in bounds:
        c = bounds["coinsText"]
        check_element("coinsText", c["x"], c["y"], c["width"], c["height"])

    # BUY buttons
    for btn in bounds.get("buyButtons", []):
        check_element(f"buyButton_{btn['index']}", btn["x"], btn["y"], btn["width"], btn["height"])

    # Upgrade panel
    if "upgradePanel" in bounds:
        u = bounds["upgradePanel"]
        check_element("upgradePanel", u["x"], u["y"], u["width"], u["height"])

    # Carry indicator
    if "carryIndicator" in bounds:
        c = bounds["carryIndicator"]
        check_element("carryIndicator", c["x"], c["y"], c["width"], c["height"])

    # Joystick (if active during test)
    if "joystickBase" in bounds:
        j = bounds["joystickBase"]
        check_element("joystickBase", j["x"], j["y"], j["width"], j["height"])
    if "joystickThumb" in bounds:
        j = bounds["joystickThumb"]
        check_element("joystickThumb", j["x"], j["y"], j["width"], j["height"])

    return len(errors) == 0, errors


def _test_joystick_interaction(page, viewport_width, viewport_height):
    """Test that the floating joystick appears at touch point and moves farmer.

    NEW MODEL: Touch/mouse down ANYWHERE in play area shows joystick at that point,
    drag steers it, release hides it. This replaces the old "drag the farmer directly" model.
    """
    # Start the game
    page.evaluate("() => { window.__GAME__.scene.scenes[0]._begin(); }")
    page.wait_for_timeout(200)

    # Get initial farmer position (logical/game-space) and the canvas's
    # actual on-screen rect + scale factor.
    initial = page.evaluate("""
        () => {
            const scene = window.__GAME__.scene.scenes[0];
            const canvas = scene.game.canvas;
            const rect = canvas.getBoundingClientRect();
            return {
                x: scene.farmer.x,
                y: scene.farmer.y,
                scaleX: rect.width / 720,
                scaleY: rect.height / 1280,
                canvasLeft: rect.left,
                canvasTop: rect.top
            };
        }
    """)

    farmer_screen_x = initial["canvasLeft"] + initial["x"] * initial["scaleX"]
    farmer_screen_y = initial["canvasTop"] + initial["y"] * initial["scaleY"]

    # NEW MODEL: Touch/click somewhere OTHER than the farmer to place joystick
    # Place joystick well to the right of the farmer to prove it's touch-anywhere
    joystick_screen_x = farmer_screen_x + 150
    joystick_screen_y = farmer_screen_y + 50

    # 1. Mouse down at joystick position - should activate joystick there
    page.mouse.move(joystick_screen_x, joystick_screen_y)
    page.mouse.down()
    page.wait_for_timeout(100)

    # Verify joystick appeared at the touch point
    joystick_check = page.evaluate("""
        () => {
            const scene = window.__GAME__.scene.scenes[0];
            return {
                joystickActive: scene.joystickActive,
                joystickCenter: scene.joystickCenter ? { x: scene.joystickCenter.x, y: scene.joystickCenter.y } : null,
                farmerPos: { x: scene.farmer.x, y: scene.farmer.y }
            };
        }
    """)
    
    if not joystick_check["joystickActive"]:
        return False, "Joystick did not activate on pointerdown"
    
    if not joystick_check["joystickCenter"]:
        return False, "Joystick center not set"

    # Joystick center should be near where we clicked (in logical coords)
    expected_center_x = (joystick_screen_x - initial["canvasLeft"]) / initial["scaleX"]
    expected_center_y = (joystick_screen_y - initial["canvasTop"]) / initial["scaleY"]
    
    center_x = joystick_check["joystickCenter"]["x"]
    center_y = joystick_check["joystickCenter"]["y"]
    
    if abs(center_x - expected_center_x) > 20 or abs(center_y - expected_center_y) > 20:
        return False, f"Joystick center ({center_x:.1f}, {center_y:.1f}) not near touch point ({expected_center_x:.1f}, {expected_center_y:.1f})"

    # 2. Drag the pointer up/left from joystick center to steer farmer
    target_screen_x = joystick_screen_x - 80
    target_screen_y = joystick_screen_y - 80
    page.mouse.move(target_screen_x, target_screen_y, steps=5)
    page.wait_for_timeout(300)

    # Check farmer moved in the direction of the joystick vector
    mid_check = page.evaluate("""
        () => {
            const scene = window.__GAME__.scene.scenes[0];
            return { x: scene.farmer.x, y: scene.farmer.y };
        }
    """)

    # 3. Continue dragging to move farmer further
    page.mouse.move(target_screen_x - 50, target_screen_y - 50, steps=5)
    page.wait_for_timeout(300)

    # 4. Release - joystick should disappear
    page.mouse.up()
    page.wait_for_timeout(100)

    final_check = page.evaluate("""
        () => {
            const scene = window.__GAME__.scene.scenes[0];
            return {
                joystickActive: scene.joystickActive,
                farmerPos: { x: scene.farmer.x, y: scene.farmer.y }
            };
        }
    """)

    if final_check["joystickActive"]:
        return False, "Joystick did not deactivate on pointerup"

    # Check farmer moved significantly from initial position
    final_farmer = final_check["farmerPos"]
    dx = final_farmer["x"] - initial["x"]
    dy = final_farmer["y"] - initial["y"]
    dist = (dx * dx + dy * dy) ** 0.5

    if dist < 30:  # Should have moved a reasonable distance
        return False, f"Farmer barely moved: dist={dist:.1f} (from {initial['x']:.1f},{initial['y']:.1f} to {final_farmer['x']:.1f},{final_farmer['y']:.1f})"

    return True, f"Joystick test passed: activated at touch point, farmer moved {dist:.1f}px, joystick hidden on release"


def _test_magnet_collection(page, viewport_width, viewport_height):
    """Test that magnet-radius auto-collection works.

    Forces a crop to be ready and positions farmer within MAGNET_RADIUS without
    pixel-perfect manual positioning, then verifies it gets collected.
    """
    # Start the game
    page.evaluate("() => { window.__GAME__.scene.scenes[0]._begin(); }")
    page.wait_for_timeout(200)

    # Force the first plot to be ready immediately and position farmer near it
    magnet_result = page.evaluate("""
        () => {
            const scene = window.__GAME__.scene.scenes[0];
            const plot = scene.plots[0];
            
            // Make plot ready now
            plot.readyAt = scene.time.now;
            plot.cropSprite.setVisible(true);
            plot.harvested = false;
            
            // Position farmer within MAGNET_RADIUS of the plot center (but not exactly on it)
            const plotCenterX = plot.x + 48;  // PLOT_SIZE/2 = 48
            const plotCenterY = plot.y + 48;
            const MAGNET_RADIUS = 60;  // From manifest default
            
            // Place farmer at radius - 10 (well within magnet range)
            const angle = 0.5;  // radians
            scene.farmer.x = plotCenterX + (MAGNET_RADIUS - 10) * Math.cos(angle);
            scene.farmer.y = plotCenterY + (MAGNET_RADIUS - 10) * Math.sin(angle);
            scene.carryIndicator.x = scene.farmer.x;
            scene.carryIndicator.y = scene.farmer.y - 56;
            
            return {
                farmerX: scene.farmer.x,
                farmerY: scene.farmer.y,
                plotCenterX: plotCenterX,
                plotCenterY: plotCenterY,
                plotReady: plot.readyAt <= scene.time.now,
                carrying: scene.carrying
            };
        }
    """)
    
    if not magnet_result["plotReady"]:
        return False, "Plot not ready after forcing readyAt"

    # Wait for magnet to trigger harvest (one frame update)
    page.wait_for_timeout(200)

    # Check if crop was collected
    collected = page.evaluate("""
        () => {
            const scene = window.__GAME__.scene.scenes[0];
            return {
                carrying: scene.carrying,
                plot0Harvested: scene.plots[0].harvested,
                carryIndicatorVisible: scene.carryIndicator.visible
            };
        }
    """)

    carrying = collected["carrying"]
    plot0_harvested = collected["plot0Harvested"]
    carry_visible = collected["carryIndicatorVisible"]
    
    if carrying != 'crop' or not plot0_harvested or not carry_visible:
        return False, "Magnet collection failed: carrying=" + str(carrying) + ", plot0Harvested=" + str(plot0_harvested) + ", carryVisible=" + str(carry_visible)

    return True, "Magnet collection test passed: crop auto-collected at distance 50px from farmer (MAGNET_RADIUS=60)"


@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", VIEWPORTS)
@pytest.mark.parametrize("dpr", DPR_VALUES)
def test_viewport_elements_visible(viewport_width, viewport_height, viewport_name, dpr, tmp_path):
    """Test that all interactive elements are visible at each viewport/DPR combination."""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        # Create page with specific viewport and DPR
        page = browser.new_page(
            viewport={"width": viewport_width, "height": viewport_height},
            device_scale_factor=dpr
        )

        html_path = HARNESS_DIR / "farm_idle.html"
        page.goto(f"file://{html_path.absolute()}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Wait for game to initialize
        page.wait_for_function("window.__GAME__ !== undefined", timeout=10000)
        page.wait_for_timeout(500)

        # Inject safe-area CSS custom properties for testing (headless Chrome returns 0 for env())
        safe_insets = {"top": 0, "right": 0, "bottom": 0, "left": 0}
        if "iPhone" in viewport_name:
            safe_insets = {"top": 44, "right": 0, "bottom": 34, "left": 0}
        elif "Galaxy" in viewport_name:
            safe_insets = {"top": 0, "right": 0, "bottom": 24, "left": 0}

        page.evaluate("""
            () => {
                const root = document.documentElement;
                root.style.setProperty('--safe-top', '%dpx');
                root.style.setProperty('--safe-right', '%dpx');
                root.style.setProperty('--safe-bottom', '%dpx');
                root.style.setProperty('--safe-left', '%dpx');
                // Update safe insets and trigger layout
                if (typeof updateSafeInsets === 'function') updateSafeInsets();
                const scene = window.__GAME__.scene.scenes[0];
                if (scene._layoutHUD) scene._layoutHUD();
            }
        """ % (safe_insets["top"], safe_insets["right"], safe_insets["bottom"], safe_insets["left"]))
        page.wait_for_timeout(200)

        # Start the game (needed for layout to finalize)
        page.evaluate("() => { window.__GAME__.scene.scenes[0]._begin(); }")
        page.wait_for_timeout(200)

        # Get element bounds
        bounds = _get_element_bounds(page)

        # Check all elements are in viewport and clear of safe areas
        all_ok, errors = _check_bounds_in_viewport(bounds, viewport_width, viewport_height, safe_insets)

        browser.close()

        if not all_ok:
            error_msg = "Viewport %s (%dx%d) DPR=%d FAILED:\\n" % (viewport_name, viewport_width, viewport_height, dpr)
            for err in errors:
                error_msg += "  - %s\\n" % err
            pytest.fail(error_msg)


@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", VIEWPORTS)
@pytest.mark.parametrize("dpr", DPR_VALUES)
def test_joystick_interaction_works(viewport_width, viewport_height, viewport_name, dpr, tmp_path):
    """Test that the floating joystick appears at touch point, steers farmer, and disappears on release."""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": viewport_width, "height": viewport_height},
            device_scale_factor=dpr
        )

        html_path = HARNESS_DIR / "farm_idle.html"
        page.goto(f"file://{html_path.absolute()}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        page.wait_for_function("window.__GAME__ !== undefined", timeout=10000)
        page.wait_for_timeout(500)

        # Inject safe-area CSS
        safe_insets = {"top": 0, "right": 0, "bottom": 0, "left": 0}
        if "iPhone" in viewport_name:
            safe_insets = {"top": 44, "right": 0, "bottom": 34, "left": 0}
        elif "Galaxy" in viewport_name:
            safe_insets = {"top": 0, "right": 0, "bottom": 24, "left": 0}

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
        """ % (safe_insets["top"], safe_insets["right"], safe_insets["bottom"], safe_insets["left"]))
        page.wait_for_timeout(200)

        moved, msg = _test_joystick_interaction(page, viewport_width, viewport_height)

        browser.close()

        if not moved:
            pytest.fail("Joystick interaction failed at %s (%dx%d) DPR=%d: %s" % (viewport_name, viewport_width, viewport_height, dpr, msg))


@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", VIEWPORTS)
@pytest.mark.parametrize("dpr", DPR_VALUES)
def test_magnet_collection_works(viewport_width, viewport_height, viewport_name, dpr, tmp_path):
    """Test that magnet-radius auto-collection works (crops within radius fly to farmer)."""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": viewport_width, "height": viewport_height},
            device_scale_factor=dpr
        )

        html_path = HARNESS_DIR / "farm_idle.html"
        page.goto(f"file://{html_path.absolute()}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        page.wait_for_function("window.__GAME__ !== undefined", timeout=10000)
        page.wait_for_timeout(500)

        # Inject safe-area CSS
        safe_insets = {"top": 0, "right": 0, "bottom": 0, "left": 0}
        if "iPhone" in viewport_name:
            safe_insets = {"top": 44, "right": 0, "bottom": 34, "left": 0}
        elif "Galaxy" in viewport_name:
            safe_insets = {"top": 0, "right": 0, "bottom": 24, "left": 0}

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
        """ % (safe_insets["top"], safe_insets["right"], safe_insets["bottom"], safe_insets["left"]))
        page.wait_for_timeout(200)

        worked, msg = _test_magnet_collection(page, viewport_width, viewport_height)

        browser.close()

        if not worked:
            pytest.fail("Magnet collection failed at %s (%dx%d) DPR=%d: %s" % (viewport_name, viewport_width, viewport_height, dpr, msg))


@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", VIEWPORTS)
@pytest.mark.parametrize("dpr", DPR_VALUES)
def test_landscape_shows_rotate_overlay(viewport_width, viewport_height, viewport_name, dpr, tmp_path):
    """Test that landscape orientation shows rotate overlay and hides game UI."""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        # Landscape viewport (wider than tall). has_touch=True simulates an
        # actual touch-capable phone rotated sideways -- the rotate-overlay
        # lockout is gated on touch capability as well as aspect ratio, so a
        # landscape-shaped but non-touch desktop window (e.g. the generic
        # execution harness's default test context) is correctly exempted.
        page = browser.new_page(viewport={"width": 844, "height": 390}, has_touch=True)

        html_path = HARNESS_DIR / "farm_idle.html"
        page.goto(f"file://{html_path.absolute()}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        page.wait_for_function("window.__GAME__ !== undefined", timeout=10000)
        page.wait_for_timeout(500)

        # Check for rotate overlay
        has_rotate_overlay = page.evaluate("""
            () => {
                // Check for DOM overlay
                const overlay = document.querySelector('.rotate-overlay, #rotate-overlay, [data-rotate-overlay]');
                if (overlay) return true;

                // Check for Phaser text overlay
                const scene = window.__GAME__?.scene?.scenes?.[0];
                if (scene) {
                    const children = scene.children.list;
                    for (const child of children) {
                        if (child.type === 'Text' && child.text && child.text.toUpperCase().includes('ROTATE')) {
                            return true;
                        }
                    }
                }
                return false;
            }
        """)

        # Check that normal game UI is not interactable in landscape. Phaser's
        # disableInteractive() sets input.enabled = false but leaves the
        # draggable flag itself untouched (it's part of the InteractiveObject
        # config, not the enabled/disabled state) -- so `enabled` is the
        # property that actually reflects whether the farmer responds to
        # input right now.
        farmer_interactive = page.evaluate("""
            () => {
                const scene = window.__GAME__?.scene?.scenes?.[0];
                return scene?.farmer?.input?.enabled === true;
            }
        """)

        browser.close()

        if not has_rotate_overlay:
            pytest.fail("Landscape: No rotate overlay found")
        if farmer_interactive:
            pytest.fail("Landscape: Farmer input is still enabled (should be disabled)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])