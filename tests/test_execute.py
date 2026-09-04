from pathlib import Path

import pytest

from pipeline.execute import run_execution_report, _has_vendor_scripts

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.slow
def test_known_good_game_loads_clean(tmp_path):
    report = run_execution_report(_read("known_good_game.html"), tmp_path)
    assert report.loaded is True
    assert report.console_errors == []
    assert report.canvas_rendered is True


@pytest.mark.slow
def test_known_bad_game_reports_console_error(tmp_path):
    report = run_execution_report(_read("known_bad_game_console_error.html"), tmp_path)
    assert report.loaded is True
    assert any("MainMenuScene" in e for e in report.console_errors)
    assert report.canvas_rendered is False


@pytest.mark.slow
def test_game_over_after_real_engagement_is_not_flagged(tmp_path):
    # Real bug, found via a live paid run: a game that plays for a real session
    # and then legitimately reaches game-over (a working win/lose condition) was
    # being flagged "game over immediately" purely because the semantic check
    # snapshotted `gameOver` once at the very end of the 20s observation window,
    # ignoring the engagement the SAME observation loop had already recorded.
    report = run_execution_report(_read("known_good_game_completes_a_session.html"), tmp_path)
    assert report.loaded is True
    assert report.canvas_rendered is True
    assert not any("game over immediately" in e.lower() for e in report.console_errors)
    assert report.engagement_duration_ms and report.engagement_duration_ms > 0


@ pytest.mark.slow
def test_missing_canvas_is_detected(tmp_path):
    html = "<!DOCTYPE html><html><body>no game here</body></html>"
    report = run_execution_report(html, tmp_path)
    assert report.canvas_rendered is False


def test_has_vendor_scripts_detects_self_contained():
    """Self-contained harness HTML (with bundled Juice/Phaser) should be detected."""
    # Minimal self-contained HTML with the markers _has_vendor_scripts looks for
    self_contained_html = """
    <!DOCTYPE html>
    <html><head><title>Test</title></head><body>
    <script>
    window.Juice = { ScreenShake: class ScreenShake {} };
    class ScreenShake { constructor() {} }
    window.__GAME__ = this.game;
    </script>
    </body></html>
    """
    assert _has_vendor_scripts(self_contained_html) is True


def test_has_vendor_scripts_detects_regular_html():
    """Regular HTML without bundled vendor scripts should not be detected as self-contained."""
    regular_html = """
    <!DOCTYPE html>
    <html><head><title>Test</title></head><body>
    <script>
    class PlayScene extends Phaser.Scene { create() {} }
    var game = new Phaser.Game({ type: Phaser.AUTO, width: 400, height: 300, scene: [PlayScene] });
    window.__GAME__ = game;
    </script>
    </body></html>
    """
    assert _has_vendor_scripts(regular_html) is False


def test_has_vendor_scripts_detects_partial_markers():
    """HTML with only partial/similar markers should not be detected as self-contained."""
    # Similar but not matching markers (comments don't contain the exact marker strings)
    partial_html = """
    <!DOCTYPE html>
    <html><head><title>Test</title></head><body>
    <script>
    window.Juice = [];  // Array instead of object
    // ScreenShake class not defined here
    // Game reference pattern not used here
    </script>
    </body></html>
    """
    assert _has_vendor_scripts(partial_html) is False


def test_has_vendor_scripts_rejects_single_marker_in_comment():
    """Regression test: a comment containing a single marker should not trigger false positive.
    
    This is the exact case from the audit: a comment with 'class ScreenShake'
    should not be detected as self-contained when the other markers are absent.
    """
    # HTML with only ONE marker inside a comment - should NOT be detected
    single_marker_comment_html = """
    <!DOCTYPE html>
    <html><head><title>Test</title></head><body>
    <script>
    // TODO: implement class ScreenShake later
    var game = new Phaser.Game({ type: Phaser.AUTO, width: 400, height: 300, scene: [] });
    </script>
    </body></html>
    """
    assert _has_vendor_scripts(single_marker_comment_html) is False

    # Another case: window.Juice = { in a comment only
    juice_comment_html = """
    <!DOCTYPE html>
    <html><head><title>Test</title></head><body>
    <script>
    // Mock: window.Juice = { ScreenShake: class {} };
    class PlayScene extends Phaser.Scene { create() {} }
    var game = new Phaser.Game({ type: Phaser.AUTO, width: 400, height: 300, scene: [PlayScene] });
    window.__GAME__ = game;
    </script>
    </body></html>
    """
    assert _has_vendor_scripts(juice_comment_html) is False

    # Another case: window.__GAME__ = this.game in a comment only
    game_comment_html = """
    <!DOCTYPE html>
    <html><head><title>Test</title></head><body>
    <script>
    // Old pattern: window.__GAME__ = this.game;
    class PlayScene extends Phaser.Scene { create() {} }
    var game = new Phaser.Game({ type: Phaser.AUTO, width: 400, height: 300, scene: [PlayScene] });
    window.__GAME__ = game;
    </script>
    </body></html>
    """
    assert _has_vendor_scripts(game_comment_html) is False


def test_has_vendor_scripts_rejects_two_markers_in_comment():
    """Regression test: two markers in comments should not trigger false positive.

    The bug was that _has_vendor_scripts used simple substring matching on the
    full HTML, so a comment block containing two of the three markers would
    incorrectly return True even though the actual code doesn't bundle Juice/Phaser.
    """
    two_markers_in_comment = """
    <!DOCTYPE html>
    <html><head><title>Test</title></head><body>
    <script>
    // window.Juice = { ScreenShake: class {} };
    // window.__GAME__ = this.game;
    class PlayScene extends Phaser.Scene { create() {} }
    var game = new Phaser.Game({ type: Phaser.AUTO, width: 400, height: 300, scene: [PlayScene] });
    window.__GAME__ = game;
    </script>
    </body></html>
    """
    assert _has_vendor_scripts(two_markers_in_comment) is False
