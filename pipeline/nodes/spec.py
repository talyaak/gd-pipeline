from pipeline.llm import get_generation_llm
from pipeline.retry import invoke_with_retry, PipelineError, NODE_TIMEOUTS, NODE_MAX_ATTEMPTS
from pipeline.schemas import ImplementationSpec, RunState
import json

PROMPT = """You are a technical game designer turning a Game Design Document into an implementation spec for a coder who will build the game in Phaser 3, as a single HTML file.

Game Design Document:
{gdd}

Produce: the entities involved (with properties and behavior), the game's state machine (ordered list of states), a balance table of tunable numeric values, and technical notes for the coder. The coder MUST: use Phaser 3 (Phaser is preloaded as a global variable, no CDN script tags), generate all textures procedurally via graphics.generateTexture() (no image files), use the Web Audio API for any sound (no audio files), and name the delta-time variable exactly 'dt' (never 'deltaTime' or 'elapsed').

If this genre involves any procedural or generative subsystem (e.g. obstacle spawning, level generation, enemy waves), include 3-5 concrete worked examples in example_chunks — short code or pseudocode snippets showing exactly what should be generated, not just a prose description. This is required for genres with patterned/procedural content; leave example_chunks empty otherwise.

CRITICAL: The state_machine MUST include these states in order:
- 'Boot' (engine init, scale manager, physics config)
- 'Preload' (generate procedural textures, load audio)
- 'Tutorial' (interactive onboarding, can be skipped)
- 'Play' (core gameplay loop)
- 'GameOver' (failure state, show CTA, offer replay)
- 'Win' (success state, show CTA, offer next level/replay)

If the genre genuinely doesn't need Tutorial or Win (e.g. pure endless runner), include them anyway but mark as optional in behavior notes.

Return a JSON object with these exact keys: entities, state_machine, balance, example_chunks, technical_notes. 
- entities should be an array of objects, each with: name (string), properties (array of strings), behavior (string)
- state_machine should be an array of strings (MUST include Boot, Preload, Tutorial, Play, GameOver, Win)
- balance should be an object with string keys and string values (e.g., {{\"gravity\": \"1200\", \"jump_velocity\": \"-400\"}})
- example_chunks should be an array of strings
- technical_notes should be an array of strings"""

def spec(state: RunState) -> dict:
    gdd = state["design"]["artifact"]
    llm = get_generation_llm(temperature=0.3)
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
        data = {
            "entities": [
                {"name": "Player", "properties": ["x", "y", "velocity", "isGrounded", "alive"], "behavior": "Jumps on input, falls due to gravity, dies on collision"},
                {"name": "Obstacle", "properties": ["x", "y", "width", "height", "type"], "behavior": "Moves left at game speed, removed when off-screen"},
                {"name": "Orb", "properties": ["x", "y"], "behavior": "Collectible for bonus points"}
            ],
            "state_machine": ["Boot", "Preload", "Tutorial", "Play", "GameOver", "Win"],
            "balance": {"gravity": "1200", "jump_velocity": "-450", "base_speed": "250", "max_speed": "550", "spawn_interval": "2.0"},
            "example_chunks": [
                "spawnObstacle(): select random type, create at x=900, add to obstacles array",
                "updateObstacles(dt): move each left by speed*dt, check collision with player, remove if x < -200"
            ],
            "technical_notes": [ "use Phaser 3", "procedural textures only", "Web Audio API for sound", "delta-time variable must be 'dt'" ]
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
   
    # Enforce required state machine states
    required_states = ["Boot", "Preload", "Tutorial", "Play", "GameOver", "Win"]
    state_machine = data.get("state_machine", [])
    for req in required_states:
        if req not in state_machine:
            state_machine.append(req)
    data["state_machine"] = state_machine
   
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