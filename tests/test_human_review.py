from pathlib import Path
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

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
        if self._plain_values:
            return SimpleNamespace(content=self._plain_values.pop(0))
        # For structured output path
        if self._structured_value:
            import json
            return SimpleNamespace(content=json.dumps(self._structured_value.model_dump() if hasattr(self._structured_value, 'model_dump') else self._structured_value))
        return SimpleNamespace(content="{}")


def _patch_llms(monkeypatch, design_value, good_html):
    research_value = GenreAnalysis(
        core_mechanics=["dodge"], juice=["particles"], progression="ramps up",
        common_mistakes=["too hard"], reference_games=["Some Game"],
    )
    spec_value = ImplementationSpec(
        entities=[], state_machine=["Play"], balance={}, example_chunks=[], technical_notes=["use Phaser 3"],
    )
    review_value = CodeReview(score=9, spec_fidelity_issues=[], quality_issues=[], strengths=["clean"])

    monkeypatch.setattr("pipeline.nodes.research.get_review_llm", lambda: _FakeLLM(structured_value=research_value))
    monkeypatch.setattr("pipeline.nodes.design.get_generation_llm", lambda **kw: _FakeLLM(structured_value=design_value))
    monkeypatch.setattr("pipeline.nodes.spec.get_generation_llm", lambda **kw: _FakeLLM(structured_value=spec_value))
    monkeypatch.setattr("pipeline.nodes.codegen.get_generation_llm", lambda **kw: _FakeLLM(plain_values=[good_html]))
    monkeypatch.setattr("pipeline.nodes.review.get_review_llm", lambda: _FakeLLM(structured_value=review_value))


@pytest.mark.slow
def test_resume_after_simulated_process_restart(tmp_path, monkeypatch):
    good_html = (FIXTURES / "known_good_game.html").read_text(encoding="utf-8")
    design_value = GameDesignDocument(
        title="Test Game", core_loop="dodge things", controls="Space to jump",
        mechanics=["jump"], juice=["particles"], mvp_scope="one level", win_lose_condition="survive 30s",
    )
    _patch_llms(monkeypatch, design_value, good_html)

    run_dir = tmp_path / "run"
    checkpoint_path = str(tmp_path / "checkpoint.sqlite")
    run_config = {"configurable": {"thread_id": "run1"}, "recursion_limit": 50}
    initial_input = {"brief": "test genre", "run_id": "run1", "run_dir": str(run_dir)}

    # First "process": run until it hits the human review interrupt, then simulate
    # the process exiting by closing the checkpointer connection.
    with SqliteSaver.from_conn_string(checkpoint_path) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        state = graph.invoke(initial_input, run_config)
        assert "__interrupt__" in state
        assert state["__interrupt__"][0].value["kind"] == "gdd_approval"

    # Second "process": fresh connection to the same sqlite file, fresh graph object,
    # resuming purely from persisted checkpoint state -- this is the actual resume test.
    with SqliteSaver.from_conn_string(checkpoint_path) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        final_state = graph.invoke(Command(resume={"approved": True}), run_config)

    assert final_state["design"]["status"] == "passed"
    assert final_state["code"]["status"] == "passed"


@pytest.mark.slow
def test_gdd_rejection_triggers_rework_with_feedback(tmp_path, monkeypatch):
    good_html = (FIXTURES / "known_good_game.html").read_text(encoding="utf-8")
    bad_design = GameDesignDocument(
        title="Bad Draft", core_loop="dodge things", controls="Space to jump",
        mechanics=["jump"], juice=[], mvp_scope="one level", win_lose_condition="survive 30s",
    )
    good_design = GameDesignDocument(
        title="Good Draft", core_loop="dodge things, more juice", controls="Space to jump",
        mechanics=["jump"], juice=["screen shake", "particles"], mvp_scope="one level", win_lose_condition="survive 30s",
    )

    research_value = GenreAnalysis(
        core_mechanics=["dodge"], juice=["particles"], progression="ramps up",
        common_mistakes=["too hard"], reference_games=["Some Game"],
    )
    spec_value = ImplementationSpec(
        entities=[], state_machine=["Play"], balance={}, example_chunks=[], technical_notes=["use Phaser 3"],
    )
    review_value = CodeReview(score=9, spec_fidelity_issues=[], quality_issues=[], strengths=["clean"])

    monkeypatch.setattr("pipeline.nodes.research.get_review_llm", lambda: _FakeLLM(structured_value=research_value))
    design_llm = _FakeLLM()
    design_calls = {"n": 0}

    def _get_design_llm(**kw):
        design_calls["n"] += 1
        return _FakeLLM(structured_value=bad_design if design_calls["n"] == 1 else good_design)

    monkeypatch.setattr("pipeline.nodes.design.get_generation_llm", _get_design_llm)
    monkeypatch.setattr("pipeline.nodes.spec.get_generation_llm", lambda **kw: _FakeLLM(structured_value=spec_value))
    monkeypatch.setattr("pipeline.nodes.codegen.get_generation_llm", lambda **kw: _FakeLLM(plain_values=[good_html]))
    monkeypatch.setattr("pipeline.nodes.review.get_review_llm", lambda: _FakeLLM(structured_value=review_value))

    run_dir = tmp_path / "run"
    checkpoint_path = str(tmp_path / "checkpoint.sqlite")
    run_config = {"configurable": {"thread_id": "run2"}, "recursion_limit": 50}

    with SqliteSaver.from_conn_string(checkpoint_path) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        state = graph.invoke(
            {"brief": "test genre", "run_id": "run2", "run_dir": str(run_dir)}, run_config
        )
        assert state["__interrupt__"][0].value["gdd"]["title"] == "Bad Draft"

        state = graph.invoke(Command(resume={"approved": False, "feedback": "add more juice"}), run_config)
        assert state["__interrupt__"][0].value["gdd"]["title"] == "Good Draft"

        final_state = graph.invoke(Command(resume={"approved": True}), run_config)

    assert design_calls["n"] == 2
    assert final_state["design"]["artifact"]["title"] == "Good Draft"
    assert final_state["code"]["status"] == "passed"