# PLAYABLE AD CREATOR — CURRENT STATE CONTEXT

## 1. PROJECT PURPOSE
**FACT** Multi-agent pipeline that turns a game genre/concept into a playable single-file HTML5 game (Phaser 3, no external assets) and proves it runs in real Chromium before declaring success (README.md:3-5, 12-15).

## 2. PIPELINE ARCHITECTURE
**FACT** 7-node LangGraph: `research → design → [human_review_gdd] → spec → codegen → validate_execute → review` with conditional edges for rework loops capped at `MAX_CODE_ATTEMPTS=3` (config.py:22, graph.py:15-30, 70-76).

## 3. STATE SCHEMA
**FACT** `RunState` TypedDict tracks `run_id`, `run_dir`, `brief`, and per-stage `StageResult` with `status`, `attempt`, `artifact`, `review`, `error` (schemas.py:62-80).

## 4. RESEARCH NODE
**FACT** One-shot LLM call using `REVIEW_MODEL` (config.py:13) with structured output `GenreAnalysis` (schemas.py:6-11). No rework loop (research.py:14-25).

## 5. DESIGN NODE (GDD)
**FACT** Generates `GameDesignDocument` (schemas.py:14-22) using `GENERATION_MODEL`. Supports human-in-the-loop rework via `human_review_gdd` interrupt (design.py:17-24, 27-52; human_review.py:6-20).

## 6. SPEC NODE
**FACT** One-shot conversion of GDD to `ImplementationSpec` (schemas.py:24-41) including entities, state machine, balance table, and mandatory `example_chunks` for procedural genres (spec.py:4-36).

## 7. CODEGEN NODE
**FACT** Generates single HTML file via `GENERATION_MODEL` with 16k token ceiling (config.py:35). Enforces: CDN Phaser, procedural textures only, Web Audio API, `dt` delta-time variable, class-before-use ordering (codegen.py:9-33, 64-108).

## 8. VALIDATION CATEGORIES — SYNTAX
**FACT** `pipeline.validate.check_html_game()` runs regex + `node --check` on extracted `<script>` content. Catches: missing `<!DOCTYPE html>`, banned delta-time names (`deltaTime`, `elapsedTime`, etc.), asset loader calls (`load.image`, `load.audio`, etc.), external asset file refs (.png, .mp3, etc.), missing `Phaser.Game`, missing `update()` (validate.py:26-73).

## 9. VALIDATION CATEGORIES — BUILD
**FACT** Static validator is the "build" gate; no separate bundler/compiler. JS syntax errors caught by `node --check` (validate.py:58-73). No TypeScript, no transpilation.

## 10. VALIDATION CATEGORIES — RUNTIME
**FACT** `pipeline.execute.run_execution_report()` launches real Chromium via Playwright, serves HTML on localhost, captures console errors, page errors, measures canvas rendering, input response via screenshot diff (execute.py:24-86).

## 11. VALIDATION CATEGORIES — BROWSER
**FACT** Browser harness: blocks ALL external network requests — no CDN allowlist (execute.py:10-13, 203, 51-70). Waits 2s load + 0.5s input + 1.5s post-input, takes before/after screenshots, detects input response by byte inequality.

## 12. VALIDATION CATEGORIES — GAMEPLAY
**WEAK INFERENCE** Gameplay correctness inferred from `canvas_rendered=True` + `input_response_detected=True` + zero console errors. No semantic gameplay assertions (win/lose, score, progression) validated.

## 13. VALIDATION CATEGORIES — VISUAL
**WEAK INFERENCE** Visual fidelity only checked via screenshot diff (before≠after). No pixel-perfect reference, no visual regression baseline, no headless GPU consistency guarantee.

## 14. VALIDATION CATEGORIES — TASK COMPLIANCE
**FACT** LLM `review` node scores spec fidelity/quality 1-10; runtime correctness already proven, so review focuses on design intent match (review.py:8-11, 29-56). Score ≥7 = pass.

## 15. REWORK LOOP MECHANICS
**FACT** Two independent loops: (a) `validate_execute` → `codegen` on static/runtime failure up to `MAX_CODE_ATTEMPTS`; (b) `review` → `codegen` on LLM score <7 up to `MAX_CODE_ATTEMPTS`. Both feed prior error evidence into rework prompt (graph.py:15-30, codegen.py:73-88).

## 16. HUMAN REVIEW GATE
**FACT** Optional interrupt after design (default on via `HUMAN_REVIEW_GDD=true`, config.py:22). CLI prompts approve/reject with free-text feedback; rejection loops back to `design` node with feedback incorporated (cli.py:11-23, graph.py:63-68).

## 17. PERSISTENCE & CHECKPOINTING
**FACT** `SqliteSaver` checkpoints per run (`output/<run>/checkpoint.sqlite`). Each attempt's artifacts saved to `output/<run>/<NN>_<stage>/attempt_<N>/` — attempt 1 evidence preserved even after attempt 2 succeeds (output.py:8-19, cli.py:47-53, test_pipeline_integration.py:75-79).

## 18. FIXTURES / TEST EVIDENCE
**FACT** 4 fixtures: `known_good_game.html` (passes all), `known_bad_game_asset_ref.html` (asset loader), `known_bad_game_delta_time.html` (banned var), `known_bad_game_console_error.html` (runtime ReferenceError from class ordering — static validator misses this) (fixtures/, test_validate.py:12-47).

## 19. TEST COVERAGE
**FACT** `pytest` with `@pytest.mark.slow` for browser tests. Unit tests for graph routing (test_graph_routing.py), human review resume (test_human_review.py), full pipeline repair loop (test_pipeline_integration.py:35-84). LLM calls mocked via `_FakeLLM`/`_FakeStructured`.

## 20. KEEP
- Execution-harness-as-primary-gate architecture (README.md:11-15)
- Per-attempt artifact persistence (output.py, test_pipeline_integration.py:76-79)
- Dual-model config (generation vs review) (config.py:12-13)
- Static validator catching asset/delta-time violations pre-browser (validate.py)
- Human-in-the-loop as configurable interrupt (graph.py:63-68)

## 21. IMPROVE
- **Runtime gameplay assertions**: Add semantic checks (win/lose triggered, score increments, state transitions) in `run_execution_report` beyond canvas+input.
- **Visual baseline**: Store reference screenshot per genre for regression detection.
- **Spec fidelity automation**: Deterministic checks for required entities/balance values from spec vs generated code.
- **Token budget monitoring**: Log actual tokens used vs `CODEGEN_MAX_TOKENS` to detect truncation risk.

## 22. REPLACE / REMOVE / MISSING / DANGEROUS ASSUMPTIONS / TECHNICAL DEBT / OVERENGINEERING / NEXT BOTTLENECK

| Category | Items |
|---|---|
| **REPLACE** | `node --check` syntax validation → eslint/typescript for richer static analysis (validate.py:58-73) |
| **REMOVE** | `RETRY_MAX_ATTEMPTS`/`RETRY_BASE_DELAY_SECONDS` in config.py:24-25 — unused (retry.py only handles Anthropic API errors) |
| **MISSING** | CI/CD config (no GitHub Actions), dependency lockfile, pre-commit hooks, release process |
| **DANGEROUS ASSUMPTIONS** | (1) `canvas_rendered` + `input_response` ≈ playable game (execute.py:70). (2) LLM review score ≥7 correlates with human fun (review.py:46). (3) Single `Space` keypress + center click covers all control schemes (execute.py:61-63). (4) `node --check` catches all JS errors (misses runtime ReferenceError from class ordering — test_validate.py:44-47). |
| **TECHNICAL DEBT** | No structured logging; `print()` in CLI. No metrics/telemetry. `config.py` mixes env defaults with comments-as-docs. `execute.py` hardcodes 127.0.0.1 + port allocation — flaky under parallel runs. |
| **OVERENGINEERING** | LangGraph + SqliteSaver for 7-node linear-ish pipeline; could be simple Python loop. `StageResult` TypedDict with `total=False` allows missing keys silently. |
| **NEXT BOTTLENECK** | **Token truncation in codegen**: 16k tokens may still truncate complex genres (config.py:33-35 comment admits 8192 was insufficient). No truncation detection or summary-based re-prompting. |

## 23. WHAT CLAUDE BUILT vs ACTUAL vs INTENDED
**FACT** Built: Working end-to-end pipeline with real browser execution gate, per-attempt persistence, human-in-the-loop, bounded rework loops, mocked test suite. **ACTUAL**: Generates games that load, render canvas, respond to input — but gameplay depth unvalidated; static validator misses class-ordering runtime errors; no CI. **INTENDED**: "Proves the result actually runs before calling it done" (README.md:14-15) — achieved for runtime load/execute, not for gameplay correctness. **SINGLE NEXT ACTION**: Add semantic gameplay assertions in `run_execution_report` (e.g., wait for win/lose state, verify score increases, confirm state machine transitions) to close the gameplay validation gap.