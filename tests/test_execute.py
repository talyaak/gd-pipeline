from pathlib import Path

import pytest

from pipeline.execute import run_execution_report

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


@pytest.mark.slow
def test_missing_canvas_is_detected(tmp_path):
    html = "<!DOCTYPE html><html><body>no game here</body></html>"
    report = run_execution_report(html, tmp_path)
    assert report.canvas_rendered is False
