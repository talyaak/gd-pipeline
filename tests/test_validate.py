from pathlib import Path

from pipeline.validate import check_html_game

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_known_good_game_has_no_issues():
    issues = check_html_game(_read("known_good_game.html"))
    assert issues == []


def test_asset_reference_is_flagged():
    issues = check_html_game(_read("known_bad_game_asset_ref.html"))
    assert any("asset" in i.lower() for i in issues)


def test_banned_delta_time_name_is_flagged():
    issues = check_html_game(_read("known_bad_game_delta_time.html"))
    assert any("deltaTime" in i for i in issues)


def test_missing_doctype_is_flagged():
    issues = check_html_game("<html><body>not a game</body></html>")
    assert any("DOCTYPE" in i for i in issues)


def test_missing_phaser_game_is_flagged():
    html = "<!DOCTYPE html><html><script>function update(t,d){}</script></html>"
    issues = check_html_game(html)
    assert any("Phaser.Game" in i for i in issues)


def test_missing_update_is_flagged():
    html = "<!DOCTYPE html><html><script>new Phaser.Game({});</script></html>"
    issues = check_html_game(html)
    assert any("update" in i for i in issues)


def test_static_validation_cannot_catch_runtime_errors():
    # Real M1 output that throws a class-ordering ReferenceError in-browser; static regex can't see it.
    issues = check_html_game(_read("known_bad_game_console_error.html"))
    assert issues == []
