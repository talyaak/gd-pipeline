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


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])