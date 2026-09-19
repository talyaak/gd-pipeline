"""
Intro-hint tests for farm_idle (Wire issue #2, red-dot regression). The
intro hint (a pulsing ring + small dot, both colored 0xe65100 -- the
farmer's own color) is shown at boot to draw attention to the farmer, then
was previously destroyed by a fixed 2500ms delayedCall. That timer was
found to run roughly 2.7x slower than real wall-clock time in this
environment, stranding the ring+dot at the farmer's boot spawn point for
several real seconds while the farmer moved away -- exactly what Tal
reported: "red dot is remnant of initial tween but not sticked to player."

Covers, per the round's acceptance numbering:
  1. ring+dot follow the farmer's position if he moves by any path while the hint is alive
  2. hint is destroyed on first real player input, well before the 2500ms nominal timer
  3. no 0xe65100 ring/dot objects persist after dismissal, and none remain stranded
     at the boot-spawn position after extended play past the old timer

Item 2 is checked across BOTH real input paths that reach _activateJoystick
(mouse click and touchscreen tap) -- not just one -- per Instinct's explicit
gate requirement that a single-path test isn't proof of a shared choke point.
"""
import pytest
from playwright.sync_api import sync_playwright
from farm_idle_test_support import _boot


def _red_circles(page):
    return page.evaluate("""() => {
        const scene = window.__GAME__.scene.scenes[0];
        return scene.children.list.filter(o => o.type === 'Arc' && o.fillColor === 0xe65100)
            .map(o => ({ radius: Math.round(o.radius), x: Math.round(o.x), y: Math.round(o.y) }));
    }""")


@pytest.mark.slow
def test_intro_hint_follows_farmer_every_frame():
    """Item 1: while the intro hint is alive, its ring+dot must track the
    farmer's CURRENT position every frame, not stay pinned to his boot
    spawn point. Moves the farmer programmatically (not via input) to
    isolate this from the separate dismiss-on-input behavior covered by
    the other tests."""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True
        )
        _boot(page, "iPhone_12_tall_contrast")

        before = _red_circles(page)
        farmer_before = page.evaluate("() => { const s = window.__GAME__.scene.scenes[0]; return { x: Math.round(s.farmer.x), y: Math.round(s.farmer.y) }; }")

        page.evaluate("""() => {
            const scene = window.__GAME__.scene.scenes[0];
            scene.farmer.x += 200;
            scene.farmer.y += 50;
        }""")
        page.wait_for_timeout(50)

        after = _red_circles(page)
        farmer_after = page.evaluate("() => { const s = window.__GAME__.scene.scenes[0]; return { x: Math.round(s.farmer.x), y: Math.round(s.farmer.y) }; }")

        browser.close()

        assert len(before) == 3, f"expected 3 red circles (ring, dot, farmer) at boot, got {before}"
        hint_circles = [c for c in after if c["radius"] != 32]
        assert len(hint_circles) == 2, f"expected ring+dot still present after farmer moved, got {after}"
        for c in hint_circles:
            assert c["x"] == farmer_after["x"] and c["y"] == farmer_after["y"], (
                f"hint circle {c} did not follow the farmer's new position "
                f"{farmer_after} (was at {farmer_before})"
            )


@pytest.mark.slow
def test_intro_hint_dismissed_on_first_input_both_paths():
    """Item 2: the hint must be destroyed on the FIRST real player input,
    well before the 2500ms nominal timer -- checked on BOTH real input
    paths that can reach _activateJoystick (mouse click and touchscreen
    tap), not just one, so passing isn't an accident of testing a single
    path."""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])

        # Path A: mouse click (desktop-style pointer input)
        page = browser.new_page(
            viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True
        )
        _boot(page, "iPhone_12_tall_contrast")
        before_mouse = _red_circles(page)
        page.mouse.click(195, 400)
        page.wait_for_timeout(50)
        after_mouse = _red_circles(page)
        page.close()

        # Path B: touchscreen tap (mobile touch input) -- fresh page
        page2 = browser.new_page(
            viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True
        )
        _boot(page2, "iPhone_12_tall_contrast")
        before_touch = _red_circles(page2)
        page2.touchscreen.tap(195, 400)
        page2.wait_for_timeout(50)
        after_touch = _red_circles(page2)
        page2.close()

        browser.close()

        assert len(before_mouse) == 3, f"expected 3 red circles before mouse input, got {before_mouse}"
        assert len(after_mouse) == 1 and after_mouse[0]["radius"] == 32, (
            f"intro hint not dismissed on mouse click (well under 2500ms): {after_mouse}"
        )
        assert len(before_touch) == 3, f"expected 3 red circles before touch input, got {before_touch}"
        assert len(after_touch) == 1 and after_touch[0]["radius"] == 32, (
            f"intro hint not dismissed on touchscreen tap (well under 2500ms): {after_touch}"
        )


@pytest.mark.slow
def test_intro_hint_no_stranding_after_extended_play():
    """Item 3: reproduces the exact original bug report -- start a
    joystick drag (real input) and move the farmer away. Checked at TWO
    points: almost immediately after the drag (200ms -- long before even
    the OLD 2500ms nominal timer could plausibly fire, so this alone is a
    reliable, timing-independent proof that dismissal happens on input,
    not on a race against a timer whose real firing speed was found to
    vary run to run in this environment, not a fixed multiple), and again
    after a generous extended wait (10s -- well past the old timer under
    any observed firing speed) to confirm nothing reappears or lingers.
    No 0xe65100 ring/dot objects may persist at either point, and none may
    remain stranded at the farmer's original boot-spawn position."""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True
        )
        _boot(page, "iPhone_12_tall_contrast")

        farmer_boot = page.evaluate("() => { const s = window.__GAME__.scene.scenes[0]; return { x: Math.round(s.farmer.x), y: Math.round(s.farmer.y) }; }")

        page.mouse.move(195, 400)
        page.mouse.down()
        page.wait_for_timeout(50)
        page.mouse.move(300, 500)
        page.wait_for_timeout(50)
        page.mouse.up()

        page.wait_for_timeout(200)
        soon_after = _red_circles(page)

        page.wait_for_timeout(10000)  # generous extended-play margin
        final = _red_circles(page)

        browser.close()

        assert len(soon_after) == 1 and soon_after[0]["radius"] == 32, (
            f"hint not dismissed promptly on input (checked at 200ms, long before any "
            f"plausible timer firing): {soon_after}"
        )
        assert len(final) == 1 and final[0]["radius"] == 32, (
            f"stray 0xe65100 hint object(s) persisted after extended play: {final}"
        )
        assert not (final[0]["x"] == farmer_boot["x"] and final[0]["y"] == farmer_boot["y"]), (
            f"the one remaining red circle is stranded at the boot-spawn position "
            f"{farmer_boot} instead of being the moved farmer: {final}"
        )