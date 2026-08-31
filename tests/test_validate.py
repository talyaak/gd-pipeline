from pathlib import Path

import pytest

from pipeline.validate import SyntaxCheckUnavailable, check_html_game

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
    # The specific runtime error (class-ordering ReferenceError) should not be caught statically
    # but semantic validation requirements may now be flagged
    assert not any("ReferenceError" in i or "class-ordering" in i for i in issues)
    # Should still catch asset/external reference issues if present


def test_mraid_ready_call_is_flagged():
    html = (
        "<!DOCTYPE html><html><script>\n"
        "new Phaser.Game({});\n"
        "function update(t, d) {}\n"
        "mraid.ready();\n"
        "</script></html>"
    )
    issues = check_html_game(html)
    assert any("ready" in i.lower() for i in issues)


def test_comment_explaining_mraid_ready_is_not_flagged():
    # Real bug: our own codegen prompt's example code includes the explanatory
    # comment "never call mraid.ready() yourself" — the banned-call regex was
    # matching that comment text itself, rejecting code that correctly never
    # actually calls mraid.ready(). Comments must not trigger banned-call checks.
    html = (
        "<!DOCTYPE html><html><script>\n"
        "new Phaser.Game({});\n"
        "// MRAID gating - gate gameplay on ready + viewable, never call mraid.ready()\n"
        "function update(t, d) {}\n"
        "</script></html>"
    )
    issues = check_html_game(html)
    assert not any("ready" in i.lower() for i in issues)


def test_missing_node_raises_instead_of_silently_passing(monkeypatch):
    # A missing `node` executable must never be indistinguishable from "syntax check passed".
    monkeypatch.setattr("pipeline.validate.shutil.which", lambda _name: None)
    with pytest.raises(SyntaxCheckUnavailable):
        check_html_game(_read("known_good_game.html"))
