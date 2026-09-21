# Architecture

Single-process Python CLI wrapping one LangGraph `StateGraph`. No servers, no queues; state lives in a SQLite checkpoint per run.

## Pipeline stages

All nodes in `pipeline/graph.py`, wiring in `build_graph()` (graph.py:1606-1679). State type: `PipelineState` (graph.py:98-118), a `TypedDict` carrying every artifact + attempt counters.

| # | Stage | Node(s) | Produces |
|---|-------|---------|----------|
| 1 | Genre Research | `research_genre` | `GenreAnalysis` |
| 2 | GDD | `generate_gdd` -> `review_gdd` -> (`human_review_gdd` HITL) | `GameDesignDocument` + `GddReview` |
| 3 | Impl Spec | `generate_impl_spec` -> `review_impl_spec` -> (`human_review_impl_spec` HITL) | `ImplementationSpec` + `ImplSpecReview` |
| 4 | Code Gen | `generate_code` (3-pass) | `GeneratedGame` (single HTML file) |
| 5 | Code Review | `review_code` | `CodeReview` |
| 6 | Vision | `verify_vision` (Playwright screenshot; review stubbed) | screenshot + synthetic pass review |
| 7 | Playtest | `run_playtest` (headless 30s input simulation + LLM analysis) | telemetry + advisory `CodeReview` |

## Data flow between agents

- Sequential artifact refinement: `GenreAnalysis` JSON -> fed into GDD prompt -> `GameDesignDocument` JSON -> fed into Impl Spec prompt -> both fed into code gen prompts -> HTML fed to review/vision/playtest.
- Structured (non-code) LLM calls use `with_structured_output(..., method="function_calling")` and `invoke_with_retry` (graph.py:145, 233, 373, 593, 673, 1219, 1571). Code-gen passes are the exception: plain text via `_run_code_pass` -> `llm.invoke` (graph.py:785-788).
- Rework loops feed the previous artifact + a structured feedback section back into the same generator node with a dedicated `REWORK_*_PROMPT` (graph.py:185, 525, 1013). Human feedback is injected as "HUMAN REVIEWER (highest priority)" (graph.py:204-223).
- Each node persists artifacts immediately via `pipeline.output.save` into `output/<genre>_<ts>/<step>/attempt_N/` — output is the de-facto inter-run store; graph state is the in-run store.

## Control flow details

- GDD cycle: auto-review fail -> regenerate (max 3 attempts, graph.py:88) -> forced to HITL after max; human reject -> regenerate with `gdd_attempt` reset to 0 (graph.py:464).
- Impl spec cycle: auto-review fail -> **no auto-retry**, goes straight to human review (graph.py:720-725) — deliberate token saving.
- Code cycle: fail -> rework prompt (max 3 attempts, graph.py:90), then forced on to vision.
- Vision/playtest are effectively terminal: vision fail after 2 attempts continues to playtest (graph.py:1406-1409); playtest always ends the graph (graph.py:1600).
- HITL: `interrupt()` (LangGraph) + `SqliteSaver` checkpointer; the CLI loop in `pipeline/cli.py:257-274` polls `state.tasks` for interrupts and resumes with `Command(resume=...)`.
- Known wiring oddity: `verify_vision` has BOTH a fixed edge to `run_playtest` (graph.py:1673) and conditional edges (graph.py:1674). Effective behavior depends on LangGraph's handling of mixed edges — UNKNOWN, not verified.

## Model topology (pipeline/graph.py:39-71)

- GEN_MODEL: generation (GDD, impl spec, code) — temperature 0.3-0.7, max_tokens up to 32,768 capped by `_MODEL_OUTPUT_LIMITS`.
- REVIEW_MODEL: research + all reviews — temperature 0.3, max_tokens 512-2048.
- VISION_MODEL: currently only used for a never-executed structured call (vision review is stubbed, graph.py:1372-1386).
- All three default to `"openrouter/free"`; routed through OpenRouter's OpenAI-compatible API with `HTTP-Referer`/`X-Title` headers.
