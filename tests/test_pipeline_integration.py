from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.graph import build_graph
from pipeline.schemas import CodeReview, GameDesignDocument, GenreAnalysis, ImplementationSpec

FIXTURES = Path(__file__).parent.parent / "fixtures"


class _FakeStructured:
    def __init__(self, value):
        self._value = value

    def invoke(self, _prompt):
        return self._value


class _FakeLLM:
    def __init__(self, structured_value=None, plain_values=None):
        self._structured_value = structured_value
        self._plain_values = list(plain_values or [])

    def with_structured_output(self, _schema, method=None):
        return _FakeStructured(self._structured_value)

    def invoke(self, _prompt):
        if "Return ONLY a JSON array of edits" in _prompt:
            # The bad->good fixture pair used by this test is a near-total rewrite
            # (missing MRAID/CTA structure entirely, not a one-line fix), so a real
            # model would correctly decline to patch it — an empty edit list makes
            # codegen's patch loop bail out immediately and fall back to full
            # regeneration, same as it would for a genuinely unpatchable diff.
            return SimpleNamespace(content="[]")
        if self._plain_values:
            return SimpleNamespace(content=self._plain_values.pop(0))
        # For structured output path
        if self._structured_value:
            import json
            return SimpleNamespace(content=json.dumps(self._structured_value.model_dump() if hasattr(self._structured_value, 'model_dump') else self._structured_value))
        return SimpleNamespace(content="{}")


@pytest.mark.slow
def test_full_pipeline_repairs_a_first_attempt_failure(tmp_path, monkeypatch):
    """Forces codegen to produce a bad-asset-ref game on attempt 1 (caught by the
    deterministic validator, no browser needed) and a clean game on attempt 2, then
    checks the graph actually loops back through codegen with the static-check
    evidence and reaches a passing state on the second attempt."""
    bad_html = (FIXTURES / "known_bad_game_asset_ref.html").read_text(encoding="utf-8")
    good_html = (FIXTURES / "known_good_game.html").read_text(encoding="utf-8")

    research_value = GenreAnalysis(
        core_mechanics=["dodge"], juice=["particles"], progression="ramps up",
        common_mistakes=["too hard early"], reference_games=["Some Game"],
    )
    design_value = GameDesignDocument(
        title="Test Game", core_loop="dodge things", controls="Space to jump",
        mechanics=["jump"], juice=["particles"], mvp_scope="one level", win_lose_condition="survive 30s",
    )
    spec_value = ImplementationSpec(
        entities=[], state_machine=["Play"], balance={}, example_chunks=[],
        technical_notes=["use Phaser 3"],
    )
    review_value = CodeReview(score=8, spec_fidelity_issues=[], quality_issues=[], strengths=["clean"])

    monkeypatch.setattr("pipeline.nodes.research.get_review_llm", lambda node: _FakeLLM(structured_value=research_value))
    monkeypatch.setattr("pipeline.nodes.design.get_generation_llm", lambda **kw: _FakeLLM(structured_value=design_value))
    monkeypatch.setattr("pipeline.nodes.spec.get_generation_llm", lambda **kw: _FakeLLM(structured_value=spec_value))
    codegen_llm = _FakeLLM(plain_values=[bad_html, good_html])
    monkeypatch.setattr("pipeline.nodes.codegen.get_generation_llm", lambda **kw: codegen_llm)
    monkeypatch.setattr("pipeline.nodes.review.get_review_llm", lambda node: _FakeLLM(structured_value=review_value))
    # The playability check makes a real (vision) LLM call as the last gate in
    # validate_execute — stub it out so this test stays a pure unit test of the
    # graph's rework routing, not an integration test of the agent itself (which
    # spawns a real subprocess and costs real money).
    from pipeline.schemas import PlayabilityReport
    monkeypatch.setattr(
        "pipeline.playability_agent.check_playability_agentic",
        lambda html, **kw: PlayabilityReport(playable=True, reasoning="stubbed for this test"),
    )

    run_dir = tmp_path / "run"
    graph = build_graph(human_review_gdd_enabled=False)
    final_state = graph.invoke(
        {"brief": "test genre", "run_id": "run", "run_dir": str(run_dir)},
        {"recursion_limit": 50},
    )

    assert final_state["code"]["status"] == "passed"
    assert final_state["code"]["attempt"] == 2
    assert final_state["execution"]["artifact"]["canvas_rendered"] is True

    # Attempt 1's rejection evidence must survive on disk, not be overwritten by attempt 2.
    attempt1_code = (run_dir / "04_code" / "attempt_1" / "game.html").read_text(encoding="utf-8")
    attempt2_code = (run_dir / "04_code" / "attempt_2" / "game.html").read_text(encoding="utf-8")
    assert "player.png" in attempt1_code
    assert "player.png" not in attempt2_code
    # Attempt 1 is rejected by the static validator before any browser launch (artifact is None).
    attempt1_execution = (run_dir / "05_execution" / "attempt_1" / "execution.json")
    assert attempt1_execution.exists()
    assert "asset" in attempt1_execution.read_text(encoding="utf-8").lower()
    assert (run_dir / "05_execution" / "attempt_2" / "execution.json").exists()