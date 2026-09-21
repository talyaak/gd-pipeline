# Modules

## pipeline/graph.py (~1680 lines)
- Purpose: everything about the pipeline's behavior — model factory, all prompts, all nodes, conditional edges, graph wiring.
- Public surface: `build_graph(checkpointer=None)` (graph.py:1606); `PipelineState` (graph.py:98).
- Internal structure: `_make_llm` / `_max_tokens` (graph.py:69-86), per-stage prompt constants, node functions, `should_*` router functions.
- Gotchas:
  - `generate_gdd` fallback GDD (graph.py:259-309) hardcodes an endless-runner design ("...Rush", lane-switching) regardless of input genre — fires when the model returns None.
  - `review_gdd` fallback heuristic treats missing `gamification` as an issue (graph.py:396) although the schema field is Optional (schemas.py:318).
  - `verify_vision` never calls the vision model: returns a hardcoded passing 7/10 review (graph.py:1380-1386); TODO at graph.py:1377.
  - Playtest telemetry hooks never increment `score` or `actions`, so those metrics are always 0; `survival_time` is `frameCount/60` (graph.py:1459-1491, 1540-1543).
  - `should_rework_playtest` reads `state.get("playtest_review")`, a key that is never written to `PipelineState` (graph.py:1596); function effectively dead (returns END unconditionally).
  - `run_playtest` calls `PLAYTEST_PROMPT.format(..., **playtest_data)` — any extra key collision would raise KeyError (graph.py:1574-1580).

## pipeline/schemas.py (567 lines)
- Purpose: every pydantic model for structured LLM I/O.
- Public surface: `GenreAnalysis`, `GameDesignDocument`, `GddReview`, `ImplementationSpec` (+ `EntityDef`, `GameState`, `BalanceTable`, `AssetEntry`, `PropertyDef`, `BalanceParam`), `ImplSpecReview`, `GeneratedGame`, `CodeReview`, and the gamification bundle (15 classes total: `GamificationSpec` + 14 sub-models, schemas.py:11-158).
- Gotchas: all review models share the shape `passed/score/strengths/issues/suggestions` with a 7/10 pass convention; reviews double as the vision/playtest output type (graph.py:1359, 1571).

## pipeline/cli.py (351 lines)
- Purpose: process entry; orchestrates run/resume/inject, renders HITL prompts, writes final summaries.
- Public surface: `main()` (invoked unconditionally by `__main__.py`).
- Gotchas:
  - `graph.get_state(config).values` is read inside the `with SqliteSaver` block (cli.py:276); downstream key access (cli.py:279-288) only uses the already-fetched values — reading state after close crashed on sqlite3 (fixed in aff76d2).
  - `--inject-code` uses `graph.update_state(..., as_node="generate_code")` to fake a code-gen result (cli.py:167-171).
  - Genre for `--resume` is parsed from the run dir name by stripping a trailing `_YYYYMMDD_HHMMSS` (cli.py:175-184).
  - Empty HITL input defaults to "approve" (cli.py:78-79).

## pipeline/output.py (163 lines)
- Purpose: run-scoped artifact paths. `init_run(genre)` -> `output/<slug>_<YYYYMMDD_HHMMSS>/`; `save`/`save_text` write into `<step>/attempt_N/`; `save_pipeline_summary` writes `pipeline_summary.md`.
- Gotchas: module-global `_run_dir` — single-run-per-process by design; `save` asserts `init_run`/`init_resume` was called first.

## pipeline/retry.py (29 lines)
- Purpose: `invoke_with_retry` — 3 attempts, exponential backoff 2s/4s, on `APIConnectionError`/`APITimeoutError`/`RateLimitError`.
- Gotchas: does not retry on generic API errors or auth failures; a model returning `None` (structured-output miss) passes through — nodes handle it with fallbacks.

## pipeline/validate.py (142 lines)
- Purpose: static, token-free checks on generated HTML. Returns list of issue strings.
- Checks (validate.py:33-110): `<script>` present/non-empty; banned dt names (`deltaTime`, `elapsed`, `deltaT`, `elapsedTime`); external asset file references; `this.load.*` calls; Node `--check` syntax check when node is on PATH; `Phaser.Game`/`Phaser.Scene`/`update` presence; `generateTexture` presence; Canvas-2D methods on Phaser Graphics (`g.save()`, `g.translate()`, etc.).
- Used by: `generate_code` for best-of-N pass selection (graph.py:1088-1110) and `review_code` as a fail-fast gate (graph.py:1194-1214).

## pipeline/__main__.py
- 4-line shim: `from pipeline.cli import main; main()` — `main()` runs at import, so importing the module executes the CLI.

## No other code
- No tests, no CI config, no scripts dir. README.md is a single line (`# gd-pipeline`). Source of truth for behavior is graph.py.
