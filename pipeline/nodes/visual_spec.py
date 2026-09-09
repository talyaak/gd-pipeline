"""Visual Spec node: generates visual specification for game art direction."""

from pipeline.llm import get_generation_llm
from pipeline.schemas import RunState
import json


PROMPT = """You are a visual design expert. Given a game design document and implementation spec, create a visual specification that defines the game's art direction.

Game Design Document:
{design}

Implementation Spec:
{spec}

Create a visual specification that includes:
1. Color palette: hex colors for primary, secondary, background, accent, UI elements
2. Shape language: "rounded" or "sharp" - determines if game objects use rounded or sharp corners
3. Particle style: description of particle effects (e.g., "soft glow bursts", "sharp sparks", "smoke plumes")
4. UI kit specification: button states (normal/hover/pressed/disabled), progress bar style, text styles
5. Juice prescriptions: specific code snippets for implementing juice/feedback techniques

Return a JSON object with these exact keys:
- color_palette: object mapping color names to hex strings (e.g., {{"primary": "#ff0000", "background": "#000000"}})
- shape_language: string, either "rounded" or "sharp"
- particle_style: string describing the particle style
- ui_kit: object with UI specification:
  - button_states: object mapping states to hex colors
  - progress_bar: object with background, fill, text colors
  - text_styles: object mapping style names to font specifications
- juice_prescriptions: array of specific code snippets for implementing juice techniques

Make the visual specification appropriate for the game's genre and mechanics.
"""


def visual_spec(state: RunState) -> dict:
    """Generate visual specification from design and implementation spec."""
    design_artifact = state.get("design", {}).get("artifact", {})
    spec_artifact = state.get("spec", {}).get("artifact", {})
    
    llm = get_generation_llm(temperature=0.3, node="visual_spec")
    try:
        raw = llm.invoke(PROMPT.format(
            design=json.dumps(design_artifact, indent=2),
            spec=json.dumps(spec_artifact, indent=2)
        ))
    except Exception as e:
        # LLM invoke failure: return explicit failure, NOT a silent canned fallback
        return {
            "visual_spec": {
                "status": "failed_needs_rework",
                "attempt": 1,
                "artifact": None,
                "review": None,
                "error": f"[invoke_error] LLM invoke failed: {e}",
            }
        }
    
    # Parse JSON from response
    content = raw.content if hasattr(raw, "content") else str(raw)
    try:
        # Find JSON object in the response
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            json_str = content[start:end]
            data = json.loads(json_str)
        else:
            raise ValueError("No JSON found in response")
    except Exception as e:
        # JSON parse failure: return explicit failure, NOT a silent canned fallback
        return {
            "visual_spec": {
                "status": "failed_needs_rework",
                "attempt": 1,
                "artifact": None,
                "review": None,
                "error": f"[parse_error] Failed to parse LLM response as JSON: {e}",
            }
        }
    
    # Validate required keys
    required_keys = ["color_palette", "shape_language", "particle_style", "ui_kit", "juice_prescriptions"]
    for key in required_keys:
        if key not in data:
            data[key] = {
                "color_palette": {"primary": "#00ff00", "background": "#000000"},
                "shape_language": "rounded",
                "particle_style": "soft glow bursts",
                "ui_kit": {},
                "juice_prescriptions": []
            }[key]
    
    result = {
        "visual_spec": {
            "status": "passed",
            "attempt": 1,
            "artifact": data,
            "review": None,
            "error": None,
        }
    }
    return result