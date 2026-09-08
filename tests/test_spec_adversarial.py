"""Adversarial tests for spec.py silent-fallback fix.

A broken-mock LLM must produce an explicit failure (failed_needs_rework),
never the canned entity spec as if it were real.
"""

import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from pipeline.nodes.spec import spec


class _BrokenLLM:
    """LLM that returns invalid JSON to trigger the parse-fallback path."""
    def __init__(self, bad_content: str):
        self._content = bad_content

    def invoke(self, _prompt):
        return SimpleNamespace(content=self._content)


def _base_state(tmp_path: Path) -> dict:
    return {
        "run_dir": str(tmp_path),
        "design": {
            "artifact": {
                "title": "Test Game",
                "core_loop": "jump over obstacles",
                "controls": "Space to jump",
                "mechanics": ["jump", "obstacle spawning"],
                "juice": ["particles", "screen shake"],
                "mvp_scope": "one level",
                "win_lose_condition": "survive 30s",
            }
        },
    }


def test_json_parse_failure_returns_failed_needs_rework_not_canned_spec(tmp_path, monkeypatch):
    """A JSON parse error must return failed_needs_rework, not the silent canned fallback."""
    # LLM returns malformed JSON (missing closing brace)
    bad_json = '{"entities": [{"name": "Player"}'
    
    monkeypatch.setattr(
        "pipeline.nodes.spec.get_generation_llm",
        lambda **kw: _BrokenLLM(bad_json),
    )
    
    result = spec(_base_state(tmp_path))
    
    # MUST fail explicitly, not silently substitute canned entity spec
    assert result["spec"]["status"] == "failed_needs_rework"
    assert result["spec"]["artifact"] is None
    assert "json" in result["spec"]["error"].lower() or "parse" in result["spec"]["error"].lower()
    
    # Verify it's NOT the canned fallback (which would have 3 entities including Player, Obstacle, Orb)
    canned_entities = [
        {"name": "Player", "properties": ["x", "y", "velocity", "isGrounded", "alive"]},
        {"name": "Obstacle", "properties": ["x", "y", "width", "height", "type"]},
        {"name": "Orb", "properties": ["x", "y"]}
    ]
    if result["spec"]["artifact"] is not None:
        entities = result["spec"]["artifact"].get("entities", [])
        # Check that we didn't get the canned fallback
        assert entities != canned_entities, "Got canned fallback instead of proper failure"


def test_llm_invoke_exception_returns_failed_needs_rework(tmp_path, monkeypatch):
    """An LLM invoke exception must return failed_needs_rework via invoke_with_retry."""
    class _RaisingLLM:
        def invoke(self, _prompt):
            raise RuntimeError("LLM API unavailable")
    
    monkeypatch.setattr(
        "pipeline.nodes.spec.get_generation_llm",
        lambda **kw: _RaisingLLM(),
    )
    
    # Also need to ensure invoke_with_retry exhausts retries quickly
    import pipeline.nodes.spec as spec_module
    original_invoke = spec_module.invoke_with_retry
    
    def _fast_fail(fn, node, timeout_seconds, max_attempts):
        try:
            return fn()
        except Exception as e:
            from pipeline.retry import PipelineError, ErrorCategory
            raise PipelineError(
                category=ErrorCategory.TRANSIENT,
                message=str(e),
                recoverable=True,
                node=node,
                attempt=max_attempts,
            )
    
    monkeypatch.setattr(spec_module, "invoke_with_retry", _fast_fail)
    
    result = spec(_base_state(tmp_path))
    
    # MUST fail explicitly
    assert result["spec"]["status"] == "failed_needs_rework"
    assert result["spec"]["artifact"] is None
    assert "llm api unavailable" in result["spec"]["error"].lower() or "transient" in result["spec"]["error"].lower()


def test_valid_json_passes(tmp_path, monkeypatch):
    """Valid JSON response should still pass."""
    valid_spec = {
        "entities": [
            {"name": "Player", "properties": ["x", "y"], "behavior": "moves"}
        ],
        "state_machine": ["Boot", "Preload", "Tutorial", "Play", "GameOver", "Win"],
        "mraid_state_machine": ["loading", "ready", "visible", "playing", "paused", "gameover"],
        "balance": {"gravity": "1000", "jump_velocity": "-400"},
        "example_chunks": [],
        "technical_notes": ["use Phaser 3"],
        "target_session_seconds": 30,
        "tutorial_duration_seconds": 5,
        "time_to_first_interaction_target_seconds": 3,
    }
    
    class _GoodLLM:
        def invoke(self, _prompt):
            return SimpleNamespace(content=json.dumps(valid_spec))
    
    monkeypatch.setattr(
        "pipeline.nodes.spec.get_generation_llm",
        lambda **kw: _GoodLLM(),
    )
    
    result = spec(_base_state(tmp_path))
    
    assert result["spec"]["status"] == "passed"
    assert result["spec"]["artifact"] is not None
    assert result["spec"]["artifact"]["entities"][0]["name"] == "Player"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])