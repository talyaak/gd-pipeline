"""Adversarial graph-level integration tests for front-half failure routing.

These tests inject REAL node failures (e.g. JSON parse failures) and verify the
graph stops at give_up without running downstream nodes. This proves the
conditional edges work end-to-end, not just the router functions in isolation.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.graph import build_graph


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
            return SimpleNamespace(content="[]")
        if self._plain_values:
            return SimpleNamespace(content=self._plain_values.pop(0))
        if self._structured_value:
            import json

            return SimpleNamespace(
                content=json.dumps(
                    self._structured_value.model_dump()
                    if hasattr(self._structured_value, "model_dump")
                    else self._structured_value
                )
            )
        return SimpleNamespace(content="{}")


@pytest.mark.slow
def test_research_json_parse_failure_stops_the_run_with_no_shipped_artifact(tmp_path, monkeypatch):
    """Inject a real JSON parse failure in research and verify the run stops at give_up.

    This test ONLY mocks the research LLM to return malformed JSON (exercising
    research.py's actual parse-failure path). It does NOT mock design/spec/visual_spec/
    codegen/review LLMs. If the conditional edges work, those nodes should never run,
    so the test passes without mocking them. If the test needs extra mocks, the fix is wrong.
    """
    # Malformed JSON - not valid JSON at all, triggers research.py's parse error path
    malformed_json_llm = _FakeLLM(plain_values=["this is not json at all"])

    monkeypatch.setattr("pipeline.nodes.research.get_review_llm", lambda node: malformed_json_llm)

    run_dir = tmp_path / "run"
    graph = build_graph(human_review_gdd_enabled=False)

    final_state = graph.invoke(
        {"brief": "test genre", "run_id": "run", "run_dir": str(run_dir)},
        {"recursion_limit": 50},
    )

    # Research should have failed with a parse error
    assert final_state["research"]["status"] == "failed_needs_rework"
    assert "parse" in final_state["research"]["error"].lower() or "syntax" in final_state["research"]["error"].lower()

    # Design should never have run (key absent or empty)
    assert "design" not in final_state or final_state["design"] == {}

    # Code should be marked as failed_max_attempts via give_up
    assert final_state["code"]["status"] == "failed_max_attempts"

    # No execution artifact should exist (nothing was executed/shipped)
    assert "execution" not in final_state or not final_state["execution"].get("artifact")