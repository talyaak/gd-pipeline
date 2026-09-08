"""Adversarial tests for validate_execute gzip gate and syntax check guard.

Bug (a): The size gate must measure final_html (post-injection), not pre-injection HTML.
Bug (b): check_html_game raising SyntaxCheckUnavailable must fail cleanly, not crash.
"""

from pipeline.nodes.validate_execute import validate_execute
from pipeline.schemas import ExecutionReport, PlayabilityReport
from pipeline.validate import SyntaxCheckUnavailable


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

# This HTML is small pre-injection but will exceed 500KB after vendor injection
# (simulating a case where pre-injection passes but post-injection fails)
SMALL_PRE_LARGE_POST_HTML = GOOD_HTML


def _state(html=GOOD_HTML):
    return {
        "run_dir": "/tmp/does-not-matter",
        "code": {"attempt": 1, "artifact": {"html": html}},
        "spec": {"artifact": {}},
    }


def _clean_report(final_html=None, **overrides):
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
        final_html=final_html or GOOD_HTML,
    )
    defaults.update(overrides)
    return ExecutionReport(**defaults)


def test_gzip_size_gate_measures_final_html_not_pre_injection(monkeypatch):
    """Bug (a): gzip size must be measured against report.final_html (post-injection),
    not the pre-injection HTML passed to run_execution_report.
    
    This test simulates a case where pre-injection HTML is small (<500KB) but
    final_html after vendor injection exceeds 500KB. The gate must catch this."""
    # Create a "large" final_html that would exceed 500KB when gzipped
    # Need ~800KB+ raw incompressible data to exceed 500KB gzipped
    import random
    import string
    large_data = ''.join(random.choices(string.ascii_letters + string.digits, k=800_000))
    final_html_large = f"<!DOCTYPE html><html><head><script>{large_data}</script></head><body><script>window.__GAME__ = new Phaser.Game({{}});</script></body></html>"
    
    # Mock report with large final_html
    report = _clean_report(final_html=final_html_large)
    monkeypatch.setattr("pipeline.nodes.validate_execute.run_execution_report", lambda html, out_dir: report)
    monkeypatch.setattr(
        "pipeline.playability_agent.check_playability_agentic",
        lambda html, **kw: PlayabilityReport(playable=True, reasoning="clearly playing"),
    )
    
    # The pre-injection HTML is small (GOOD_HTML), but final_html is large
    # OLD BUGGY BEHAVIOR: would pass because it measures pre-injection HTML
    # FIXED BEHAVIOR: must fail because final_html exceeds 500KB gzipped
    result = validate_execute(_state())
    
    assert result["execution"]["status"] == "failed_needs_rework", (
        f"Expected failed_needs_rework because final_html exceeds 500KB gzipped, "
        f"got {result['execution']['status']}"
    )
    assert "Gzipped HTML size" in result["execution"]["error"]
    assert "exceeds limit (500 KB)" in result["execution"]["error"]


def test_gzip_size_passes_when_final_html_under_limit(monkeypatch):
    """Regression test: normal games with final_html under 500KB gzipped should pass."""
    report = _clean_report(final_html=GOOD_HTML)
    monkeypatch.setattr("pipeline.nodes.validate_execute.run_execution_report", lambda html, out_dir: report)
    monkeypatch.setattr(
        "pipeline.playability_agent.check_playability_agentic",
        lambda html, **kw: PlayabilityReport(playable=True, reasoning="clearly playing"),
    )
    
    result = validate_execute(_state())
    
    assert result["execution"]["status"] == "passed", (
        f"Expected passed for small final_html, got {result['execution']['status']}: {result['execution']['error']}"
    )


def test_syntax_check_unavailable_fails_cleanly_not_crash(monkeypatch):
    """Bug (b): check_html_game raising SyntaxCheckUnavailable must be caught and
    reported as a clean 'failed_needs_rework' with an explicit error message,
    NOT crash the graph with an unhandled exception.
    
    This simulates `node` being missing from PATH."""
    def _raise_syntax_check_unavailable(*args, **kwargs):
        raise SyntaxCheckUnavailable("`node` executable not found on PATH — cannot run JS syntax check")
    
    monkeypatch.setattr("pipeline.nodes.validate_execute.check_html_game", _raise_syntax_check_unavailable)
    
    # This must NOT raise an exception; it must return a failed_needs_rework result
    result = validate_execute(_state())
    
    assert result["execution"]["status"] == "failed_needs_rework", (
        f"Expected failed_needs_rework, got {result['execution']['status']}"
    )
    assert "JS syntax check unavailable" in result["execution"]["error"]
    assert "node" in result["execution"]["error"].lower()


def test_syntax_check_unavailable_does_not_silently_pass(monkeypatch):
    """Ensures SyntaxCheckUnavailable is never swallowed into a pass.
    
    The old behavior (if unguarded) would crash the graph. A worse bug would be
    catching and returning empty issues = silent pass. This test ensures neither
    happens."""
    def _raise_syntax_check_unavailable(*args, **kwargs):
        raise SyntaxCheckUnavailable("`node` executable not found on PATH")
    
    monkeypatch.setattr("pipeline.nodes.validate_execute.check_html_game", _raise_syntax_check_unavailable)
    
    result = validate_execute(_state())
    
    # Must be explicit failure, never "passed"
    assert result["execution"]["status"] != "passed", "SyntaxCheckUnavailable must never result in passed status"
    assert result["execution"]["status"] == "failed_needs_rework"
    assert result["execution"]["error"] is not None
    assert "syntax" in result["execution"]["error"].lower() or "node" in result["execution"]["error"].lower()


def test_static_issues_still_work_after_syntax_guard(monkeypatch):
    """Ensure normal static validation issues (not SyntaxCheckUnavailable) still work."""
    # Return some static issues without raising
    monkeypatch.setattr("pipeline.nodes.validate_execute.check_html_game", 
                        lambda html: ["Missing Phaser.Game instantiation"])
    
    result = validate_execute(_state())
    
    assert result["execution"]["status"] == "failed_needs_rework"
    assert "Phaser.Game" in result["execution"]["error"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])