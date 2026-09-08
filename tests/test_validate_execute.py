from pipeline.nodes.validate_execute import validate_execute
from pipeline.playability_agent import PlayabilitySkipped
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


def test_playability_failure_fails_an_otherwise_clean_run(monkeypatch):
    report = _clean_report()
    monkeypatch.setattr("pipeline.nodes.validate_execute.run_execution_report", lambda html, out_dir: report)
    monkeypatch.setattr(
        "pipeline.playability_agent.check_playability_agentic",
        lambda html, **kw: PlayabilityReport(playable=False, reasoning="frozen on start screen"),
    )

    result = validate_execute(_state())

    assert result["execution"]["status"] == "failed_needs_rework"
    assert "frozen on start screen" in result["execution"]["error"]


def test_playability_error_is_treated_as_failure_not_a_pass(monkeypatch):
    report = _clean_report()
    monkeypatch.setattr("pipeline.nodes.validate_execute.run_execution_report", lambda html, out_dir: report)

    def _raise(*a, **kw):
        raise RuntimeError("agent subprocess unreachable")

    monkeypatch.setattr("pipeline.playability_agent.check_playability_agentic", _raise)

    result = validate_execute(_state())

    assert result["execution"]["status"] == "failed_needs_rework"
    assert "errored" in result["execution"]["error"].lower()


def test_playability_not_invoked_when_runtime_already_failed(monkeypatch):
    report = _clean_report(console_errors=["some real runtime error"])
    monkeypatch.setattr("pipeline.nodes.validate_execute.run_execution_report", lambda html, out_dir: report)

    def _must_not_be_called(*a, **kw):
        raise AssertionError("playability check should not run when runtime checks already failed")

    monkeypatch.setattr("pipeline.playability_agent.check_playability_agentic", _must_not_be_called)

    result = validate_execute(_state())

    assert result["execution"]["status"] == "failed_needs_rework"
    assert "some real runtime error" in result["execution"]["error"]


def test_fully_clean_and_playable_passes(monkeypatch):
    report = _clean_report()
    monkeypatch.setattr("pipeline.nodes.validate_execute.run_execution_report", lambda html, out_dir: report)
    monkeypatch.setattr(
        "pipeline.playability_agent.check_playability_agentic",
        lambda html, **kw: PlayabilityReport(playable=True, reasoning="clearly playing"),
    )

    result = validate_execute(_state())

    assert result["execution"]["status"] == "passed"


def test_playability_skipped_when_claude_cli_missing(monkeypatch):
    """When claude CLI is missing, playability check is SKIPPED (not failed)."""
    report = _clean_report()
    monkeypatch.setattr("pipeline.nodes.validate_execute.run_execution_report", lambda html, out_dir: report)

    def _raise_skipped(*a, **kw):
        raise PlayabilitySkipped("claude CLI not found in PATH; playability check skipped")

    monkeypatch.setattr("pipeline.playability_agent.check_playability_agentic", _raise_skipped)

    result = validate_execute(_state())

    assert result["execution"]["status"] == "skipped"
    assert "skipped" in result["execution"]["error"].lower()
    assert "claude" in result["execution"]["error"].lower()
