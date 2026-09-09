"""Adversarial tests for visual_spec.py silent-fallback fix.

A broken-mock LLM must produce an explicit failure (failed_needs_rework),
never the canned visual spec as if it were real.
"""

import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from pipeline.nodes.visual_spec import visual_spec


class _BrokenLLM:
    """LLM that returns invalid JSON to trigger the parse-fallback path."""
    def __init__(self, bad_content: str):
        self._content = bad_content

    def invoke(self, _prompt):
        return SimpleNamespace(content=self._content)


class _RaisingLLM:
    """LLM that raises an exception on invoke."""
    def __init__(self, exc: Exception):
        self._exc = exc

    def invoke(self, _prompt):
        raise self._exc


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
        "spec": {
            "artifact": {
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
        },
    }


def test_json_parse_failure_returns_failed_needs_rework_not_canned_visual_spec(tmp_path, monkeypatch):
    """A JSON parse error must return failed_needs_rework, not the silent canned fallback."""
    # LLM returns malformed JSON (missing closing brace)
    bad_json = '{"color_palette": {"primary": "#ff0000"}'
    
    monkeypatch.setattr(
        "pipeline.nodes.visual_spec.get_generation_llm",
        lambda **kw: _BrokenLLM(bad_json),
    )
    
    result = visual_spec(_base_state(tmp_path))
    
    # MUST fail explicitly, not silently substitute canned visual spec
    assert result["visual_spec"]["status"] == "failed_needs_rework"
    assert result["visual_spec"]["artifact"] is None
    assert "json" in result["visual_spec"]["error"].lower() or "parse" in result["visual_spec"]["error"].lower()
    
    # Verify it's NOT the canned fallback (check for the specific canned values)
    if result["visual_spec"]["artifact"] is not None:
        artifact = result["visual_spec"]["artifact"]
        # The canned fallback has these specific values
        assert artifact.get("color_palette", {}).get("primary") != "#00ff00", "Got canned fallback color palette"
        assert artifact.get("shape_language") != "rounded", "Got canned fallback shape language"


def test_llm_invoke_exception_returns_failed_needs_rework(tmp_path, monkeypatch):
    """An LLM invoke exception must return failed_needs_rework."""
    monkeypatch.setattr(
        "pipeline.nodes.visual_spec.get_generation_llm",
        lambda **kw: _RaisingLLM(RuntimeError("LLM API unavailable")),
    )
    
    result = visual_spec(_base_state(tmp_path))
    
    # MUST fail explicitly
    assert result["visual_spec"]["status"] == "failed_needs_rework"
    assert result["visual_spec"]["artifact"] is None
    assert "llm api unavailable" in result["visual_spec"]["error"].lower() or "runtime" in result["visual_spec"]["error"].lower()


def test_valid_json_passes(tmp_path, monkeypatch):
    """Valid JSON response should still pass."""
    valid_visual_spec = {
        "color_palette": {
            "primary": "#ff0000",
            "secondary": "#00ff00",
            "background": "#000000",
            "accent": "#ffff00",
            "ui_normal": "#aa0000",
            "ui_hover": "#cc0000",
            "ui_pressed": "#880000",
            "ui_disabled": "#555555"
        },
        "shape_language": "sharp",
        "particle_style": "sharp sparks",
        "ui_kit": {
            "button_states": {
                "normal": "#aa0000",
                "hover": "#cc0000",
                "pressed": "#880000",
                "disabled": "#555555"
            },
            "progress_bar": {
                "background": "#333333",
                "fill": "#aa0000",
                "text": "#ffffff"
            },
            "text_styles": {
                "title": {"fontSize": "32px", "fill": "#ffffff"},
                "ui": {"fontSize": "24px", "fill": "#ffffff"},
                "score": {"fontSize": "28px", "fill": "#ffff00"}
            }
        },
        "juice_prescriptions": [
            "// Particle burst: this.add.particles('spark').createEmitter({x: 100, y: 100, speed: 200, lifespan: 300});",
            "// Screen shake: this.cameras.main.shake(100, 0.01);"
        ]
    }
    
    class _GoodLLM:
        def invoke(self, _prompt):
            return SimpleNamespace(content=json.dumps(valid_visual_spec))
    
    monkeypatch.setattr(
        "pipeline.nodes.visual_spec.get_generation_llm",
        lambda **kw: _GoodLLM(),
    )
    
    result = visual_spec(_base_state(tmp_path))
    
    assert result["visual_spec"]["status"] == "passed"
    assert result["visual_spec"]["artifact"] is not None
    assert result["visual_spec"]["artifact"]["color_palette"]["primary"] == "#ff0000"
    assert result["visual_spec"]["artifact"]["shape_language"] == "sharp"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])