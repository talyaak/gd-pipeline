"""Adversarial tests for research.py and design.py silent fallbacks.

These tests verify that on LLM JSON parse failure, the nodes return
failed_needs_rework status carrying the real parse error, NOT the canned fallback.
"""
import pytest
from types import SimpleNamespace
from pipeline.nodes import research, design
from pipeline.schemas import RunState, GenreAnalysis, GameDesignDocument


class _FakeLLM:
    """Fake LLM that returns whatever content we give it."""
    def __init__(self, content):
        self.content = content
    
    def invoke(self, _prompt):
        return SimpleNamespace(content=self.content)


def test_research_json_parse_failure_returns_failed_needs_rework(monkeypatch):
    """Research node must return failed_needs_rework on JSON parse failure, not canned fallback."""
    # LLM returns malformed JSON (missing closing brace)
    bad_content = '{"core_mechanics": ["run", "jump"], "juice": ["particles"], "progression": "ramps up"'
    
    monkeypatch.setattr(
        "pipeline.nodes.research.get_review_llm",
        lambda node: _FakeLLM(bad_content)
    )
    
    state = RunState(brief="test genre", run_id="test", run_dir="/tmp/test")
    result = research.research(state)
    
    # MUST be failed_needs_rework, NOT passed with canned fallback
    assert result["research"]["status"] == "failed_needs_rework"
    assert result["research"]["artifact"] is None
    assert "error" in result["research"]
    assert result["research"]["error"] is not None
    
    # The error must contain the real parse error info (e.g., JSONDecodeError)
    error_msg = result["research"]["error"].lower()
    assert "json" in error_msg or "decode" in error_msg or "parse" in error_msg
    
    # MUST NOT contain the canned fallback values
    # Canned fallback has: core_mechanics=["run", "jump", "dodge"], reference_games=["Crossy Road", "Temple Run"]
    if result["research"]["artifact"]:
        mechanics = result["research"]["artifact"].get("core_mechanics", [])
        assert "dodge" not in mechanics, "Canned fallback 'dodge' leaked into artifact"
        ref_games = result["research"]["artifact"].get("reference_games", [])
        assert "Crossy Road" not in ref_games, "Canned fallback 'Crossy Road' leaked into artifact"
        assert "Temple Run" not in ref_games, "Canned fallback 'Temple Run' leaked into artifact"


def test_research_empty_response_returns_failed_needs_rework(monkeypatch):
    """Research node must return failed_needs_rework on empty/no JSON response."""
    bad_content = "I apologize, but I cannot fulfill this request."
    
    monkeypatch.setattr(
        "pipeline.nodes.research.get_review_llm",
        lambda node: _FakeLLM(bad_content)
    )
    
    state = RunState(brief="test genre", run_id="test", run_dir="/tmp/test")
    result = research.research(state)
    
    assert result["research"]["status"] == "failed_needs_rework"
    assert result["research"]["artifact"] is None
    assert result["research"]["error"] is not None


def test_design_json_parse_failure_returns_failed_needs_rework(monkeypatch):
    """Design node must return failed_needs_rework on JSON parse failure, not canned Endless Runner."""
    # Need research artifact first
    research_artifact = {
        "core_mechanics": ["dodge"], "juice": ["particles"], "progression": "ramps up",
        "common_mistakes": ["too hard early"], "reference_games": ["Some Game"]
    }
    
    # LLM returns malformed JSON
    bad_content = '{"title": "Test", "core_loop": "loop", "controls": "Space", "mechanics": ["jump"], "juice": ["particles"], "mvp_scope": "one level", "win_lose_condition": "survive"'
    
    monkeypatch.setattr(
        "pipeline.nodes.design.get_generation_llm",
        lambda **kw: _FakeLLM(bad_content)
    )
    
    state = RunState(
        brief="test genre",
        run_id="test",
        run_dir="/tmp/test",
        research={"status": "passed", "attempt": 1, "artifact": research_artifact, "review": None, "error": None}
    )
    result = design.design(state)
    
    # MUST be failed_needs_rework, NOT passed with canned Endless Runner
    assert result["design"]["status"] == "failed_needs_rework"
    assert result["design"]["artifact"] is None
    assert result["design"]["error"] is not None
    
    error_msg = result["design"]["error"].lower()
    assert "json" in error_msg or "decode" in error_msg or "parse" in error_msg
    
    # MUST NOT contain the canned Endless Runner fallback values
    if result["design"]["artifact"]:
        title = result["design"]["artifact"].get("title", "")
        assert title != "Endless Runner", f"Canned fallback title 'Endless Runner' leaked: {title}"
        core_loop = result["design"]["artifact"].get("core_loop", "")
        assert "Run forward, jump to dodge obstacles" not in core_loop, "Canned fallback core_loop leaked"
        controls = result["design"]["artifact"].get("controls", "")
        assert "Space/tap to jump" not in controls, "Canned fallback controls leaked"


def test_design_empty_response_returns_failed_needs_rework(monkeypatch):
    """Design node must return failed_needs_rework on empty/no JSON response."""
    research_artifact = {
        "core_mechanics": ["dodge"], "juice": ["particles"], "progression": "ramps up",
        "common_mistakes": ["too hard early"], "reference_games": ["Some Game"]
    }
    
    bad_content = "I cannot generate a GDD for this genre."
    
    monkeypatch.setattr(
        "pipeline.nodes.design.get_generation_llm",
        lambda **kw: _FakeLLM(bad_content)
    )
    
    state = RunState(
        brief="test genre",
        run_id="test",
        run_dir="/tmp/test",
        research={"status": "passed", "attempt": 1, "artifact": research_artifact, "review": None, "error": None}
    )
    result = design.design(state)
    
    assert result["design"]["status"] == "failed_needs_rework"
    assert result["design"]["artifact"] is None
    assert result["design"]["error"] is not None


def test_research_valid_json_returns_passed(monkeypatch):
    """Research node should return passed with valid artifact on valid JSON."""
    good_content = '''{
        "core_mechanics": ["run", "jump"],
        "juice": ["particles", "screen shake"],
        "progression": "Speed increases over time",
        "common_mistakes": ["Too hard early", "Unfair obstacles"],
        "reference_games": ["Crossy Road", "Temple Run"]
    }'''
    
    monkeypatch.setattr(
        "pipeline.nodes.research.get_review_llm",
        lambda node: _FakeLLM(good_content)
    )
    
    state = RunState(brief="endless runner", run_id="test", run_dir="/tmp/test")
    result = research.research(state)
    
    assert result["research"]["status"] == "passed"
    assert result["research"]["artifact"] is not None
    assert result["research"]["artifact"]["core_mechanics"] == ["run", "jump"]


def test_design_valid_json_returns_passed(monkeypatch):
    """Design node should return passed with valid artifact on valid JSON."""
    research_artifact = {
        "core_mechanics": ["dodge"], "juice": ["particles"], "progression": "ramps up",
        "common_mistakes": ["too hard early"], "reference_games": ["Some Game"]
    }
    
    good_content = '''{
        "title": "Test Game",
        "core_loop": "Dodge obstacles",
        "controls": "Space to jump",
        "mechanics": ["jump", "obstacle spawning"],
        "juice": ["particles"],
        "mvp_scope": "One level",
        "win_lose_condition": "Survive 30s"
    }'''
    
    monkeypatch.setattr(
        "pipeline.nodes.design.get_generation_llm",
        lambda **kw: _FakeLLM(good_content)
    )
    
    state = RunState(
        brief="test genre",
        run_id="test",
        run_dir="/tmp/test",
        research={"status": "passed", "attempt": 1, "artifact": research_artifact, "review": None, "error": None}
    )
    result = design.design(state)
    
    assert result["design"]["status"] == "passed"
    assert result["design"]["artifact"] is not None
    assert result["design"]["artifact"]["title"] == "Test Game"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])