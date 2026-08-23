from pipeline.llm import get_generation_llm
from pipeline.schemas import ImplementationSpec, RunState

PROMPT = """You are a technical game designer turning a Game Design Document into an \
implementation spec for a coder who will build the game in Phaser 3, as a single HTML file.

Game Design Document:
{gdd}

Produce: the entities involved (with properties and behavior), the game's state machine \
(ordered list of states), a balance table of tunable numeric values, and technical notes \
for the coder. The coder MUST: use Phaser 3 (loaded from a CDN <script> tag), generate all \
textures procedurally via graphics.generateTexture() (no image files), use the Web Audio \
API for any sound (no audio files), and name the delta-time variable exactly 'dt' (never \
'deltaTime' or 'elapsed').

If this genre involves any procedural or generative subsystem (e.g. obstacle spawning, \
level generation, enemy waves), include 3-5 concrete worked examples in example_chunks — \
short code or pseudocode snippets showing exactly what should be generated, not just a \
prose description. This is required for genres with patterned/procedural content; leave \
example_chunks empty otherwise."""


def spec(state: RunState) -> dict:
    gdd = state["design"]["artifact"]
    llm = get_generation_llm(temperature=0.3).with_structured_output(ImplementationSpec, method="function_calling")
    result: ImplementationSpec = llm.invoke(PROMPT.format(gdd=gdd))
    return {
        "spec": {
            "status": "passed",
            "attempt": 1,
            "artifact": result.model_dump(),
            "review": None,
            "error": None,
        }
    }
