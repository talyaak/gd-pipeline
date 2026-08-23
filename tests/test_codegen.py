from pathlib import Path
from types import SimpleNamespace

from pipeline.nodes.codegen import codegen


class _FakeLLM:
    def __init__(self, content: str, finish_reason: str = "stop"):
        self._content = content
        self._finish_reason = finish_reason

    def invoke(self, _prompt):
        return SimpleNamespace(content=self._content, response_metadata={"finish_reason": self._finish_reason})


def _base_state(run_dir: Path) -> dict:
    return {
        "run_dir": str(run_dir),
        "design": {"artifact": {"title": "t"}},
        "spec": {"artifact": {"entities": []}},
    }


def test_truncated_generation_fails_even_if_output_looks_valid(tmp_path, monkeypatch):
    # Cut off mid-file, but starts with <!DOCTYPE html> — the doctype check alone would miss this.
    monkeypatch.setattr(
        "pipeline.nodes.codegen.get_generation_llm",
        lambda **kw: _FakeLLM("<!DOCTYPE html><html><script>new Phaser.Game(", finish_reason="length"),
    )
    result = codegen(_base_state(tmp_path))
    assert result["code"]["status"] == "failed_needs_rework"
    assert "truncat" in result["code"]["error"].lower()


def test_complete_generation_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pipeline.nodes.codegen.get_generation_llm",
        lambda **kw: _FakeLLM("<!DOCTYPE html><html></html>", finish_reason="stop"),
    )
    result = codegen(_base_state(tmp_path))
    assert result["code"]["status"] == "passed"
