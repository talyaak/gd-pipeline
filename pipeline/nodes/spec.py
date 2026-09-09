from pipeline.llm import get_generation_llm
from pipeline.retry import invoke_with_retry, PipelineError, NODE_TIMEOUTS, NODE_MAX_ATTEMPTS
from pipeline.schemas import ImplementationSpec, RunState
import json
import os

# Prompt moved to external file for easier editing.
with open(os.path.join(os.path.dirname(__file__), 'spec_prompt.txt'), 'r') as f:
    PROMPT = f.read()

def spec(state: RunState) -> dict:
    gdd = state["design"]["artifact"]
    llm = get_generation_llm(temperature=0.3, node="spec")
    try:
        raw = invoke_with_retry(
            lambda: llm.invoke(PROMPT.format(gdd=gdd)),
            node="spec",
            timeout_seconds=NODE_TIMEOUTS.get("spec", 60),
            max_attempts=NODE_MAX_ATTEMPTS.get("spec", 2),
        )
    except PipelineError as pe:
        # Return structured error state
        return {
            "spec": {
                "status": "failed_needs_rework",
                "attempt": pe.attempt,
                "artifact": None,
                "review": None,
                "error": f"[{pe.category.value}] {pe.message}",
            }
        }
    content = raw.content if hasattr(raw, "content") else str(raw)
    try:
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
            "spec": {
                "status": "failed_needs_rework",
                "attempt": 1,
                "artifact": None,
                "review": None,
                "error": f"[parse_error] Failed to parse LLM response as JSON: {e}",
            }
        }

    # Normalize data to match schema expectations
    # Ensure entities.properties is a list of strings
    for entity in data.get("entities", []):
        if isinstance(entity.get("properties"), dict):
            entity["properties"] = list(entity["properties"].keys())
        elif not isinstance(entity.get("properties"), list):
            entity["properties"] = []
   
    # Ensure balance values are strings
    for key, value in data.get("balance", {}).items():
        data["balance"][key] = str(value)
   
    # Ensure example_chunks is a list of strings
    if not isinstance(data.get("example_chunks"), list):
        data["example_chunks"] = []
   
    # Ensure technical_notes is a list of strings
    if not isinstance(data.get("technical_notes"), list):
        data["technical_notes"] = []
   
    # Enforce required state machine states in order
    required_states = ["Boot", "Preload", "Tutorial", "Play", "GameOver", "Win"]
    state_machine = data.get("state_machine", [])
    # Keep extra states that are not in required list, preserving their original order
    extra_states = [s for s in state_machine if s not in required_states]
    # Use the required states in the correct order
    data["state_machine"] = required_states + extra_states

    # Enforce required MRAID state machine states in order
    required_mraid_states = ["loading", "ready", "visible", "playing", "paused", "gameover"]
    mraid_state_machine = data.get("mraid_state_machine", [])
    # Keep extra states that are not in required list, preserving their original order
    extra_mraid_states = [s for s in mraid_state_machine if s not in required_mraid_states]
    # Use the required states in the correct order
    data["mraid_state_machine"] = required_mraid_states + extra_mraid_states

    # Ensure timing fields exist with sensible defaults
    if "target_session_seconds" not in data or not isinstance(data["target_session_seconds"], int):
        data["target_session_seconds"] = 30
    else:
        # Clamp to valid range
        data["target_session_seconds"] = max(15, min(40, data["target_session_seconds"]))

    if "tutorial_duration_seconds" not in data or not isinstance(data["tutorial_duration_seconds"], int):
        data["tutorial_duration_seconds"] = 5
    else:
        # Clamp to valid range
        data["tutorial_duration_seconds"] = max(3, min(8, data["tutorial_duration_seconds"]))

    if "time_to_first_interaction_target_seconds" not in data or not isinstance(data["time_to_first_interaction_target_seconds"], int):
        data["time_to_first_interaction_target_seconds"] = 4
    else:
        # Clamp to valid range (must be <= 4 for retention)
        data["time_to_first_interaction_target_seconds"] = max(1, min(4, data["time_to_first_interaction_target_seconds"]))

    # --- JUICE CONTRACT IMPLEMENTATION ---
    # Extract juice from design if available and add appropriate snippets to example_chunks
    try:
        design_artifact = state.get("design", {}).get("artifact", {})
        juice_list = design_artifact.get("juice", []) if design_artifact else []
        
        # Convert juice items to code snippets
        juice_snippets = []
        for juice_item in juice_list:
            juice_lower = juice_item.lower().strip()
            if "particle" in juice_lower or "particles" in juice_lower:
                juice_snippets.append("this.add.particles('image').createEmitter({{ x: 100, y: 100, speed: 100, quantity: 20, lifespan: 500 }}); // Particle burst")
            elif "shake" in juice_lower or "screen shake" in juice_lower:
                juice_snippets.append("this.cameras.main.shake(100, 0.01); // Screen shake")
            elif "hit pause" in juice_lower or "pause" in juice_lower:
                juice_snippets.append("this.time.delayedCall(50); // Hit pause (50ms freeze)")
            elif "tween" in juice_lower or "scale" in juice_lower or "alpha" in juice_lower:
                juice_snippets.append("this.tweens.add({{ targets: sprite, scaleX: 1.2, yoyo: true, duration: 50 }}); // Visual feedback pulse")
            elif "sound" in juice_lower or "audio" in juice_lower:
                juice_snippets.append("// Audio feedback: this.sound.play('sfx_name'); // Play sound effect")
        
        # Add juice snippets to example_chunks if we generated any
        if juice_snippets:
            # Add a header comment and the snippets
            juice_chunk = "// Juice/feedback techniques - THESE ARE REQUIRED in the generated code\n" + "\n".join(juice_snippets)
            data["example_chunks"].insert(0, juice_chunk)
            
            # Add note to technical_notes
            if "IMPORTANT: Include all juice/snack feedback techniques from example_chunks" not in str(data.get("technical_notes", [])):
                data["technical_notes"].append("IMPORTANT: Include all juice/snack feedback techniques from example_chunks in your generated code")
    except Exception as e:
        # If there's any error in processing juice, continue without it
        # This ensures we don't break the spec generation if juice processing fails
        pass
   
    result = ImplementationSpec(**data)
    return {
        "spec": {
            "status": "passed",
            "attempt": 1,
            "artifact": result.model_dump(),
            "review": None,
            "error": None,
        }
    }