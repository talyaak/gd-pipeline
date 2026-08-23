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
def test_missing_canvas_is_detected(tmp_path):
    html = "<!DOCTYPE html><html><body>no game here</body></html>"
    report = run_execution_report(html, tmp_path)
    assert report.canvas_rendered is False
