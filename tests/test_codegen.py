import json
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


class _RecordingLLM:
    """Distinguishes a surgical-patch request from a full-regeneration request by
    the PATCH_PROMPT's own marker text, so tests can assert which path was taken."""

    def __init__(self, patch_response: str, regen_response: str | None = None):
        self.patch_response = patch_response
        self.regen_response = regen_response
        self.calls: list[str] = []

    def invoke(self, prompt: str):
        if "Return ONLY a JSON array of edits" in prompt:
            self.calls.append("patch")
            return SimpleNamespace(content=self.patch_response, response_metadata={})
        self.calls.append("regen")
        return SimpleNamespace(
            content=self.regen_response or "<!DOCTYPE html><html></html>",
            response_metadata={"finish_reason": "stop"},
        )


def test_rework_converges_via_surgical_patch_without_full_regen(tmp_path, monkeypatch):
    previous_html = (
        "<!DOCTYPE html>\n"
        "<html><body><script>\n"
        "class PlayScene extends Phaser.Scene {\n"
        "  constructor() { super('PlayScene'); }\n"
        "  update(time, elapsedTime) {\n"
        "    const dt = elapsedTime / 1000;\n"
        "  }\n"
        "}\n"
        "var game = new Phaser.Game({ scene: [PlayScene] });\n"
        "</script></body></html>"
    )
    edits = [{
        "old_string": "  update(time, elapsedTime) {\n    const dt = elapsedTime / 1000;\n  }",
        "new_string": "  update(time, dt) {\n    this.game.sessionTime = (this.game.sessionTime || 0) + dt;\n  }",
    }]
    fake_llm = _RecordingLLM(patch_response=json.dumps(edits))
    monkeypatch.setattr("pipeline.nodes.codegen.get_generation_llm", lambda **kw: fake_llm)

    state = _base_state(tmp_path)
    state["code"] = {
        "status": "failed_needs_rework", "attempt": 1, "artifact": {"html": previous_html},
        "review": None, "error": "static validation failed: banned delta-time name",
    }
    state["execution"] = {
        "status": "failed_needs_rework", "attempt": 1,
        "artifact": {"loaded": True, "console_errors": [], "canvas_rendered": True, "input_response_detected": True},
        "error": None,
    }

    result = codegen(state)

    assert fake_llm.calls == ["patch"], "should converge on the first patch round and never fall back to full regen"
    assert result["code"]["surgical_patch_used"] is True
    assert result["code"]["status"] == "passed"
    assert result["code"]["attempt"] == 2
    assert "elapsedTime" not in result["code"]["artifact"]["html"]


def test_rework_falls_back_to_full_regen_when_patch_loop_cannot_converge(tmp_path, monkeypatch):
    previous_html = "<!DOCTYPE html><html><script>broken</script></html>"
    fake_llm = _RecordingLLM(patch_response="not valid json at all", regen_response="<!DOCTYPE html><html>regenerated</html>")
    monkeypatch.setattr("pipeline.nodes.codegen.get_generation_llm", lambda **kw: fake_llm)

    state = _base_state(tmp_path)
    state["code"] = {
        "status": "failed_needs_rework", "attempt": 1, "artifact": {"html": previous_html},
        "review": None, "error": "static validation failed",
    }
    state["execution"] = {"status": "failed_needs_rework", "attempt": 1, "artifact": {}, "error": "static validation failed"}

    result = codegen(state)

    assert "patch" in fake_llm.calls
    assert "regen" in fake_llm.calls
    assert result["code"]["surgical_patch_used"] is False
    assert result["code"]["attempt"] == 2
    assert result["code"]["artifact"]["html"] == "<!DOCTYPE html><html>regenerated</html>"
