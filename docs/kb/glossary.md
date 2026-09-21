# Glossary

Terms as used in this repo, with code-grounded definitions.

- **Cycle X** — The pipeline's core loop pattern: generate -> review -> fix -> repeat until the quality threshold is met or attempts are exhausted. Named in graph.py:11 and commit ae4bee0.
- **GDD** — Game Design Document. Structured design artifact (`GameDesignDocument`, schemas.py:245) produced in Step 2; the creative brief for the game.
- **Implementation Spec (impl spec)** — Technical blueprint (`ImplementationSpec`, schemas.py:445) between GDD and code: entities, state machine, balance tables, scene flow, asset manifest, `example_chunks`.
- **HITL** — Human-in-the-loop. LangGraph `interrupt()` pauses (graph.py:443, 741) so a human can approve/fix/feedback via the CLI before expensive downstream steps.
- **Genre research** — Step 1 output (`GenreAnalysis`, schemas.py:161): mechanics, juice patterns, retention hooks, reference games for the target genre.
- **Juice / game feel** — Concrete game-feel effects (screen shake, hit-freeze, particles, tweens, pitch-varied audio). The GDD must list parameterized juice items (`juice_list`, schemas.py:296); Pass 3 of code gen implements them (graph.py:943).
- **Hyper-casual** — Target genre class: instant-play web games with 1-2 inputs for portals like CrazyGames/Poki/itch.io (graph.py:124-138).
- **Chunk** — A spawn-pattern JSON object (`example_chunks`, schemas.py:494-502) used by endless-runner-style games; the code gen implements a "chunk sequencer" cycling them (graph.py:810-811, 888-890).
- **generateTexture** — Phaser's method for baking procedural textures from Graphics; the mandated replacement for external sprite files (validate.py:89-94).
- **dt rule** — The game loop must derive `dt = delta / 1000`; variables named `deltaTime`/`elapsed`/etc. are banned and detected by validate.py:15-16, 52-57.
- **Coyote time / jump buffer** — Platformer feel parameters (0.08s grace after leaving ground / 0.12s queued jump input) that code-gen prompts hard-require (graph.py:827-829).
- **Fair spawning** — Spawn rule: at least 2 adjacent lanes clear, obstacles spawn off-screen right, dt-based (never setInterval) — graph.py:894-900.
- **Hit-freeze** — 50ms `physics.world.pause()` on damaging collision, a mandatory juice item (graph.py:980-983).
- **DDA** — Dynamic Difficulty Adjustment (`DynamicDifficultyConfig`, schemas.py:52-64): runtime tuning toward a target failure rate.
- **Octalysis / Hook Model / SDT** — Gamification frameworks structurally encoded in schemas.py:11-50 (core drives, trigger-action-reward-investment, autonomy/competence/relatedness); bundled in `GamificationSpec`.
- **Phaser 3** — The mandated game engine for generated games (single-file HTML, arcade physics); enforced by validation checks (validate.py:79-87).
- **BootScene** — Code-gen convention: first scene that generates all textures then transitions onward (graph.py:806).
- **OpenRouter** — The LLM gateway used for all models via OpenAI-compatible API (graph.py:43, 74-86).
- **Gen / Review / Vision model** — The three env-configurable model roles (`GEN_MODEL`, `REVIEW_MODEL`, `VISION_MODEL`, graph.py:46-50).
- **Run / run dir** — One pipeline execution's artifact directory `output/<genre_slug>_<YYYYMMDD_HHMMSS>/` (output.py:32-39), containing zero-padded step folders with `attempt_N` subfolders.
- **Checkpointer** — LangGraph `SqliteSaver` at `<run_dir>/.checkpoint.sqlite` enabling crash resume and HITL interrupts (cli.py:234-237).
- **--inject-code** — CLI escape hatch to substitute an externally authored HTML file as the code-gen output and resume at review (cli.py:145-172, aff76d2).
- **FORCED** — CLI display term for a stage that exhausted its attempts and was passed anyway (cli.py:329-338).
- **Best-of-N (passes)** — In multi-pass code gen, keeping the pass with the fewest validation issues (graph.py:1088-1110).
- **Validation gate** — The token-free static checks (`check_html_game`, validate.py:33) run before LLM code review.
