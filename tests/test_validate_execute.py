from pipeline.nodes.validate_execute import validate_execute
from pipeline.schemas import ExecutionReport, PlayabilityReport

GOOD_HTML = (
    "<!DOCTYPE html><html><script>\n"
    "class PlayScene extends Phaser.Scene {\n"
    "  constructor() { super('PlayScene'); }\n"
    "  update(time, delta) {\n"
    "    const dt = delta / 1000;\n"
    "    this.game.sessionTime = (this.game.sessionTime || 0) + delta;\n"
    "  }\n"
    "}\n"
    "window.__GAME__ = new Phaser.Game({ scene: [PlayScene] });\n"
    "window.__GAME__.registry.set('score', 0);\n"
    "</script></html>"
)


def _state(html=GOOD_HTML):
    return {
        "run_dir": "/tmp/does-not-matter",
        "code": {"attempt": 1, "artifact": {"html": html}},
        "spec": {"artifact": {}},
    }


def _clean_report(**overrides):
    defaults = dict(
        loaded=True,
        console_errors=[],
        canvas_rendered=True,
        input_response_detected=True,
        screenshot_before_path="/tmp/before.png",
        screenshot_after_path="/tmp/after.png",
        duration_ms=26500,
        time_to_first_interaction_ms=1000,
        engagement_duration_ms=20000,
        completion_rate=1.0,
        final_html=GOOD_HTML,
    )
    defaults.update(overrides)
    return ExecutionReport(**defaults)


def test_playability_failure_fails_an_otherwise_clean_run(tmp_path, monkeypatch):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    before.write_bytes(b"fake")
    after.write_bytes(b"fake")
    report = _clean_report(screenshot_before_path=str(before), screenshot_after_path=str(after))

    monkeypatch.setattr("pipeline.nodes.validate_execute.run_execution_report", lambda html, out_dir: report)
    monkeypatch.setattr(
        "pipeline.playability.check_playability",
        lambda before_png, after_png, node="playability": PlayabilityReport(playable=False, reasoning="frozen on start screen"),
    )

    result = validate_execute(_state())

    assert result["execution"]["status"] == "failed_needs_rework"
    assert "frozen on start screen" in result["execution"]["error"]


def test_playability_error_is_treated_as_failure_not_a_pass(tmp_path, monkeypatch):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    before.write_bytes(b"fake")
    after.write_bytes(b"fake")
    report = _clean_report(screenshot_before_path=str(before), screenshot_after_path=str(after))

    monkeypatch.setattr("pipeline.nodes.validate_execute.run_execution_report", lambda html, out_dir: report)

    def _raise(*a, **kw):
        raise RuntimeError("vision API unreachable")

    monkeypatch.setattr("pipeline.playability.check_playability", _raise)

    result = validate_execute(_state())

    assert result["execution"]["status"] == "failed_needs_rework"
    assert "errored" in result["execution"]["error"].lower()


def test_playability_not_invoked_when_runtime_already_failed(tmp_path, monkeypatch):
    report = _clean_report(console_errors=["some real runtime error"])
    monkeypatch.setattr("pipeline.nodes.validate_execute.run_execution_report", lambda html, out_dir: report)

    def _must_not_be_called(*a, **kw):
        raise AssertionError("playability check should not run when runtime checks already failed")

    monkeypatch.setattr("pipeline.playability.check_playability", _must_not_be_called)

    result = validate_execute(_state())

    assert result["execution"]["status"] == "failed_needs_rework"
    assert "some real runtime error" in result["execution"]["error"]


def test_fully_clean_and_playable_passes(tmp_path, monkeypatch):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    before.write_bytes(b"fake")
    after.write_bytes(b"fake")
    report = _clean_report(screenshot_before_path=str(before), screenshot_after_path=str(after))

    monkeypatch.setattr("pipeline.nodes.validate_execute.run_execution_report", lambda html, out_dir: report)
    monkeypatch.setattr(
        "pipeline.playability.check_playability",
        lambda before_png, after_png, node="playability": PlayabilityReport(playable=True, reasoning="clearly playing"),
    )

    result = validate_execute(_state())

    assert result["execution"]["status"] == "passed"
