from pathlib import Path
from types import SimpleNamespace

from pipeline.nodes.review import review


class _FakeLLM:
    def __init__(self, content: str):
        self._content = content

    def invoke(self, _prompt):
        return SimpleNamespace(content=self._content)


def _base_state(run_dir: Path) -> dict:
    return {
        "run_dir": str(run_dir),
        "design": {"artifact": {"title": "t"}},
        "spec": {"artifact": {"entities": []}},
        "code": {"attempt": 1, "artifact": {"html": "<!DOCTYPE html>...</html>"}},
        "execution": {"artifact": {"loaded": True, "canvas_rendered": True, "input_response_detected": True}},
    }


def test_malformed_review_response_fails_instead_of_fabricating_pass(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.nodes.review.get_review_llm", lambda: _FakeLLM("not json at all"))
    result = review(_base_state(tmp_path))
    assert result["code"]["status"] == "failed_needs_rework"
    assert result["code"]["review"]["score"] < 7
    assert "unparseable" in result["code"]["review"]["quality_issues"][0].lower()


def test_valid_review_response_still_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pipeline.nodes.review.get_review_llm",
        lambda: _FakeLLM('{"score": 9, "spec_fidelity_issues": [], "quality_issues": [], "strengths": ["clean"]}'),
    )
    result = review(_base_state(tmp_path))
    assert result["code"]["status"] == "passed"
