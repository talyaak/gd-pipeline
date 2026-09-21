# Agents

All "agents" are LangGraph nodes in `pipeline/graph.py` sharing one `PipelineState` (graph.py:98-118). There is no multi-agent framework — each role is a prompt + structured-output model. Communication = state fields + JSON serialized into the next prompt.

## Orchestrator
- Not an LLM. The graph wiring (`build_graph`, graph.py:1606) + the CLI interrupt loop (`pipeline/cli.py:257-274`) + the `should_*` conditional-edge functions route between roles.
- Contracts: reads `*_review.passed`/`score` and attempt counters; enforces `MAX_GDD_ATTEMPTS=3`, `MAX_IMPL_SPEC_ATTEMPTS=2` (unused — impl spec never auto-retries), `MAX_CODE_ATTEMPTS=3`, `MAX_VISION_ATTEMPTS=2`, `MAX_PLAYTEST_ATTEMPTS=1` (graph.py:88-92).

## Designer (genre research + GDD)
- `research_genre`: REVIEW_MODEL, temp 0.3 (graph.py:141-154). Output contract: `GenreAnalysis` (schemas.py:161-207).
- `generate_gdd`: GEN_MODEL, temp 0.7 (graph.py:226-314). Contract: `GameDesignDocument` (schemas.py:245-321). On rework, uses `REWORK_GDD_PROMPT` with previous GDD + human/auto feedback (graph.py:185-201, 204-223).
- Prompt priorities baked in (graph.py:160-182): fun in 3s, 1-2 inputs, free/procedural assets, MVP-first, mandatory parameterized juice.

## Design Judge (GDD review)
- `review_gdd`: REVIEW_MODEL, temp 0.3 (graph.py:369-412). Contract: `GddReview`. Weighted rubric: specificity 3x, core loop 2x, scope 2x, fun 2x, juice 1x; pass >= 7 (graph.py:320-366). Plus a coherence check: N lanes require N-1 lateral inputs; every mechanic needs a matching control (graph.py:346-353).

## Spec Writer / Spec Judge
- `generate_impl_spec` (GEN_MODEL, graph.py:586-625) -> `ImplementationSpec` (schemas.py:445-507); ingests unresolved GDD review issues to stop gap propagation (graph.py:550-563).
- `review_impl_spec` (REVIEW_MODEL, graph.py:669-717) -> `ImplSpecReview`. MVP-lenient rubric; pass >= 7; fail routes to human, not auto-rework (graph.py:720-725).

## Coder
- `generate_code` (GEN_MODEL, temp 0.3, graph.py:1056-1125). First attempt = 3 passes:
  - Pass 1 FOUNDATION (graph.py:791-868): full working game, controls-first wiring, init-order rule, procedural textures, Web Audio, physics-feel CONFIG.
  - Pass 2 SYSTEMS (graph.py:871-940): pooling, fair spawning, difficulty ramp, localStorage, HUD, parallax, hitboxes.
  - Pass 3 JUICE (graph.py:943-1010): implements every `gdd.juice_list` item + baseline polish.
  - Best-of-N between passes selected by lowest `check_html_game` issue count (graph.py:1088-1110).
- Rework attempt = `REWORK_CODE_PROMPT` with reviewer's issues (graph.py:1013-1053, 1066-1077).
- Contract: raw single-file HTML (`<!DOCTYPE html>` ... `</html>`), wrapped in `GeneratedGame` (schemas.py:514-530).

## Code Judge
- `review_code` (REVIEW_MODEL, graph.py:1185-1258) -> `CodeReview`. Rubric: runtime correctness 4x, core loop 3x, juice 2x, spec fidelity 1x, plus controls audit and init-order check (graph.py:1131-1182). Skips the LLM entirely when validation issues exist (see gates.md).

## Human (HITL participant)
- `human_review_gdd` / `human_review_impl_spec` nodes call LangGraph `interrupt()` (graph.py:443, 741); CLI renders and collects `approve`/`fix`/free-text (cli.py:76-92, 126-142). `fix` converts reviewer issues+suggestions into the feedback string (1b9d804). Approve keywords: approve/a/y/yes/ok/lgtm (graph.py:458).
- Human feedback travels in `state.human_feedback`, consumed by the next generator run, then cleared (graph.py:314).

## QA roles (uncommitted work)
- Vision Verifier: `verify_vision` — Playwright screenshot at 720x1280, 3s settle (graph.py:1332-1340); LLM review NOT yet wired (stub returns pass, graph.py:1380-1386).
- Playtest Analyst: `run_playtest` — headless Chromium with injected telemetry script + random tap/swipe/hold inputs for 30s (graph.py:1444-1567); `PLAYTEST_PROMPT` analyzes telemetry (graph.py:1415-1441). Advisory only — never blocks (graph.py:1600).
