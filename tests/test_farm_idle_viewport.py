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

    return len(errors) == 0, errors


def _test_touch_drag(page, viewport_width, viewport_height):
    """Test that touch drag moves the farmer correctly.

    Uses mouse-simulated pointer events (not page.touchscreen, which requires
    has_touch=True on the browser context and isn't needed here -- Phaser's
    input plugin treats mouse and touch pointers the same way). Farmer
    position is read in FIT-mode logical (720x1280) coordinates and must be
    converted to real on-screen pixels via the canvas's actual rendered
    rect + scale factor before driving Playwright's mouse, the same
    conversion _get_element_bounds uses for the visibility checks.
    """
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

    # Target position (move farmer to the right), in screen space
    target_x = farmer_screen_x + 100
    target_y = farmer_screen_y

    # Drag via mouse pointer events (Phaser's input plugin handles these
    # identically to touch pointers for a draggable game object).
    page.mouse.move(farmer_screen_x, farmer_screen_y)
    page.mouse.down()
    page.mouse.move(target_x, target_y, steps=5)
    page.mouse.up()
    page.wait_for_timeout(200)

    # Check farmer moved
    final = page.evaluate("""
        () => {
            const scene = window.__GAME__.scene.scenes[0];
            return { x: scene.farmer.x, y: scene.farmer.y };
        }
    """)

    moved = abs(final["x"] - initial["x"]) > 10  # Should have moved significantly
    return moved, f"Farmer moved from ({initial['x']:.1f}, {initial['y']:.1f}) to ({final['x']:.1f}, {final['y']:.1f})"


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

        page.evaluate(f"""() => {{
            const root = document.documentElement;
            root.style.setProperty('--safe-top', '{safe_insets["top"]}px');
            root.style.setProperty('--safe-right', '{safe_insets["right"]}px');
            root.style.setProperty('--safe-bottom', '{safe_insets["bottom"]}px');
            root.style.setProperty('--safe-left', '{safe_insets["left"]}px');
            // Update safe insets and trigger layout
            if (typeof updateSafeInsets === 'function') updateSafeInsets();
            const scene = window.__GAME__.scene.scenes[0];
            if (scene._layoutHUD) scene._layoutHUD();
        }}""")
        page.wait_for_timeout(200)

        # Start the game
        page.evaluate("() => { window.__GAME__.scene.scenes[0]._begin(); }")
        page.wait_for_timeout(200)

        # Get element bounds
        bounds = _get_element_bounds(page)

        # Check all elements are in viewport and clear of safe areas
        all_ok, errors = _check_bounds_in_viewport(bounds, viewport_width, viewport_height, safe_insets)

        browser.close()

        if not all_ok:
            error_msg = f"Viewport {viewport_name} ({viewport_width}x{viewport_height}) DPR={dpr} FAILED:\\n"
            for err in errors:
                error_msg += f"  - {err}\\n"
            pytest.fail(error_msg)


@pytest.mark.slow
@pytest.mark.parametrize("viewport_width,viewport_height,viewport_name", VIEWPORTS)
@pytest.mark.parametrize("dpr", DPR_VALUES)
def test_touch_drag_works(viewport_width, viewport_height, viewport_name, dpr, tmp_path):
    """Test that touch drag moves the farmer at each viewport/DPR."""
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

        # Start the game
        page.evaluate("() => { window.__GAME__.scene.scenes[0]._begin(); }")
        page.wait_for_timeout(200)

        moved, msg = _test_touch_drag(page, viewport_width, viewport_height)

        browser.close()

        if not moved:
            pytest.fail(f"Touch drag failed at {viewport_name} ({viewport_width}x{viewport_height}) DPR={dpr}: {msg}")


@pytest.mark.slow
def test_landscape_shows_rotate_overlay(tmp_path):
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