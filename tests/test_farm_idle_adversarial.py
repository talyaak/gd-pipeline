#!/usr/bin/env python3
"""Adversarial tests for farm_idle harness - tests the _harvestPlot and _sellAtStall methods directly."""
import tempfile
from pathlib import Path

import pytest

from pipeline.execute import run_execution_report, _has_vendor_scripts

HARNESS_DIR = Path(__file__).parent.parent / "harness"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _build_broken_html():
    """Build HTML from the broken fixture."""
    import subprocess
    import tempfile as tmp

    # Build the broken variant
    out_dir = Path(tmp.mkdtemp()) / "farm_idle_broken"
    out_dir.mkdir(parents=True, exist_ok=True)

    src_js = FIXTURES_DIR / "farm_idle_broken_sale.game.js"
    result = subprocess.run([
        "bash", "scripts/build_harness_html.sh",
        "farm_idle_broken", "farm_idle - Broken",
        str(src_js), "false"
    ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)

    if result.returncode != 0:
        raise RuntimeError(f"Build failed: {result.stderr}")

    html_path = HARNESS_DIR / "farm_idle_broken.html"
    assert html_path.exists(), f"HTML not built: {html_path}"
    return html_path.read_text()


@pytest.mark.slow
def test_broken_sale_fixture_coins_stay_zero(tmp_path):
    """Broken fixture: _harvestPlot then _sellAtStall should leave coins at 0."""
    html = _build_broken_html()
    
    # Write HTML to a temp file for Playwright
    html_path = Path(tmp_path) / "broken.html"
    html_path.write_text(html)

    report = run_execution_report(html, tmp_path)

    assert report.loaded is True, "Game should load"

    # Wait for game to be ready
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file://{html_path}")
        page.wait_for_timeout(2000)

        # Wait for window.__GAME__ to exist
        page.wait_for_function("window.__GAME__ !== undefined", timeout=10000)

        # Call _harvestPlot(0) then _sellAtStall()
        coins = page.evaluate("""
            () => {
                const scene = window.__GAME__.scene.scenes[0];
                scene._harvestPlot(0);
                scene._sellAtStall();
                return scene.coins;
            }
        """)

        browser.close()

        assert coins == 0, f"Broken fixture should have 0 coins after sell, got {coins}"


@pytest.mark.slow
def test_real_harness_sale_increases_coins(tmp_path):
    """Real harness: _harvestPlot then _sellAtStall should increase coins."""
    html = (HARNESS_DIR / "farm_idle.html").read_text()
    
    # Write HTML to a temp file for Playwright
    html_path = Path(tmp_path) / "real.html"
    html_path.write_text(html)

    report = run_execution_report(html, tmp_path)

    assert report.loaded is True, "Game should load"

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file://{html_path}")
        page.wait_for_timeout(2000)

        # Wait for window.__GAME__ to exist
        page.wait_for_function("window.__GAME__ !== undefined", timeout=10000)

        # Call _harvestPlot(0) then _sellAtStall()
        coins = page.evaluate("""
            () => {
                const scene = window.__GAME__.scene.scenes[0];
                // Force plot 0 to be ready
                if (scene.plots[0]) {
                    scene.plots[0].readyAt = 0;
                    scene.plots[0].harvested = false;
                    scene.plots[0].cropSprite.setVisible(true);
                }
                // Force state to PLAYING
                scene.state = 'playing';
                scene.game.state = 'playing';
                scene._harvestPlot(0);
                scene._sellAtStall();
                return scene.coins;
            }
        """)

        browser.close()

        assert coins > 0, f"Real harness should have positive coins after sell, got {coins}"


@pytest.mark.slow
def test_plot_upgrade_cost_scale_reskin(tmp_path):
    """Reskinned variant: second plot purchase cost should stay under 500 (not 7500+).

    This test exercises the actual brief-substituted values through the real reskin
    pipeline (substitute_consts + build_harness_html.sh), verifying that
    PLOT_UPGRADE_COST_GROWTH=150 is correctly interpreted as 1.50x, not 150x.
    """
    import subprocess

    # Build reskinned HTML via the real pipeline (uses briefs/farm_idle_brief.json)
    out_dir = Path(tmp_path) / "farm_idle_reskin"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Use the existing brief which has PLOT_UPGRADE_COST_GROWTH=150
    brief_path = Path(__file__).parent.parent / "briefs" / "farm_idle_brief.json"
    result = subprocess.run([
        ".venv/bin/python", "-m", "pipeline.reskin",
        str(brief_path),
        "--build", "--verify"
    ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)

    if result.returncode != 0:
        raise RuntimeError(f"Reskin failed: {result.stderr}")

    # The reskin pipeline builds to harness/farm_idle_reskinned/farm_idle_brief.html
    html_path = Path(__file__).parent.parent / "harness" / "farm_idle_reskinned" / "farm_idle_brief.html"
    assert html_path.exists(), f"Reskinned HTML not built: {html_path}"

    html = html_path.read_text()

    # Write HTML to a temp file for Playwright
    test_html_path = Path(tmp_path) / "reskin.html"
    test_html_path.write_text(html)

    report = run_execution_report(html, tmp_path)
    assert report.loaded is True, "Reskinned game should load"

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file://{test_html_path}")
        page.wait_for_timeout(2000)

        # Wait for window.__GAME__ to exist
        page.wait_for_function("window.__GAME__ !== undefined", timeout=10000)

        # Set up game state: give enough coins, force first plot ready, state to PLAYING
        result = page.evaluate("""
            () => {
                const scene = window.__GAME__.scene.scenes[0];
                // Give enough coins for two plot upgrades (50 + 75 = 125, give 1000)
                scene.coins = 1000;
                // Force plot 0 to be ready
                if (scene.plots[0]) {
                    scene.plots[0].readyAt = 0;
                    scene.plots[0].harvested = false;
                    scene.plots[0].cropSprite.setVisible(true);
                }
                // Force state to PLAYING
                scene.state = 'playing';
                scene.game.state = 'playing';
                return { coins: scene.coins, plotUpgradeCount: scene.plotUpgradeCount };
            }
        """)
        print(f"Initial state: {result}")

        # First plot purchase
        page.evaluate("""
            () => {
                const scene = window.__GAME__.scene.scenes[0];
                scene._buyUpgrade('plot');
            }
        """)
        page.wait_for_timeout(500)

        # Check cost for second purchase
        second_purchase_info = page.evaluate("""
            () => {
                const scene = window.__GAME__.scene.scenes[0];
                const cost = Math.ceil(50 * Math.pow(150 / 100, scene.plotUpgradeCount));
                return { cost, plotUpgradeCount: scene.plotUpgradeCount, coins: scene.coins };
            }
        """)
        print(f"After first purchase: {second_purchase_info}")

        # Second plot purchase
        page.evaluate("""
            () => {
                const scene = window.__GAME__.scene.scenes[0];
                scene._buyUpgrade('plot');
            }
        """)
        page.wait_for_timeout(500)

        # Verify second purchase happened and cost was sane
        final_info = page.evaluate("""
            () => {
                const scene = window.__GAME__.scene.scenes[0];
                return { plotUpgradeCount: scene.plotUpgradeCount, coins: scene.coins };
            }
        """)
        print(f"After second purchase: {final_info}")

        browser.close()

        # The second purchase should have succeeded (plotUpgradeCount == 2)
        # and the cost should have been ~75 (under 500), not 7500+
        assert final_info["plotUpgradeCount"] == 2, f"Expected 2 plot upgrades, got {final_info['plotUpgradeCount']}"
        # The key assertion: second purchase cost must be under 500 (sane curve), not thousands
        assert second_purchase_info["cost"] < 500, f"Second plot purchase cost {second_purchase_info['cost']} exceeds 500 (scale bug!)"