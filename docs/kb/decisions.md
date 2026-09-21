# Decision Log

Reconstructed from `git log --all` (all SHAs verified). Chronological. "Uncommitted" entries verified via `git status`/`git diff HEAD`.

| SHA | Decision | Evidence / apparent reason |
|-----|----------|---------------------------|
| 9c6eeb3 | Project bootstrapped (main branch). | `git log`: "first commit", 2026-02-27, talyaak. |
| 962132f | Build pipeline as a single LangGraph node: Genre Research. | Commit subject "Add Step 1: Genre Research Agent (single LangGraph node)". |
| 768cb6b | Research node switched from Claude to GPT-4o. | Commit subject; cost/speed implied, exact reason UNKNOWN. |
| 4e43b94 | Persist every step's output as JSON under `output/`. | Commit subject "Save pipeline output to output/ directory as JSON files"; basis of output.py. |
| 547a5b9 | Add GDD generation (Step 2). | Commit subject. |
| ae4bee0 | Introduce Cycle X (generate -> review -> fix loop) on GDD. | Commit subject "Add Cycle X review loop to GDD generation step". |
| bc8561f | Add HITL human approval gate on GDD; Cycle X on impl spec. | Commit subject; human control before committing to code gen. |
| bfa083e | Save full GDD draft during HITL so the human can review in an editor. | Commit subject; CLI still saves `gdd_for_review.json` (cli.py:43). |
| 918d44b | Add Implementation Spec step (Step 3) bridging design and code. | Commit subject. |
| 6b97e2b | Reshape ImplementationSpec schema for OpenAI structured-output compatibility. | Commit subject "Fix ImplementationSpec schema for OpenAI structured output". |
| 8488f5f | Add code gen (Step 4), code review (Step 5), and run-scoped output management. | Commit subject. |
| 6c933c3 | Harden code-gen/review prompts against runtime errors. | Commit subject; prompted by generated games crashing at runtime. |
| cdff53b | Add token-free static validation gate before LLM review; trim prompts. | Commit subject; explicit goal in validate.py docstring "without an LLM call... save tokens" (validate.py:3-5). |
| 0ac1c5a | Switch stack to gpt-5.2 and Phaser 3; ban external asset references. | Commit subject; enforced in code by validate.py asset checks (validate.py:19-31, 59-73). |
| c640e6e | Raise max_tokens for gpt-5.2 reasoning overhead. | Commit subject. |
| 3e53c7d | Suppress langchain Pydantic V1 deprecation warnings. | Commit subject; cli.py:14-22 filters. |
| 1b9d804 | Add `fix` option to HITL prompt: one keystroke applies reviewer issues+suggestions. | Commit subject; implemented cli.py:84-92, 134-142. |
| e0a6895 | Manual quality work by the human author. | Commit subject "some manual work towards quality improvement"; scope UNKNOWN (no body). |
| c6acacb | Fix schema error; token optimizations. | Commit subject. This commit (not aff76d2) is what PR #1 merged to origin/main. |
| ff91386 | Merge PR #1 (claude/ai-game-pipeline-UHrBZ up to c6acacb) into main. | Merge commit, 2026-04-12. |
| aff76d2 | Major overhaul (on branch, NOT in origin/main): 3-pass code generation (foundation -> systems -> juice) with best-of-N selection; `--inject-code` resume flag; per-model max_tokens cap table; sqlite3 closed-DB fix; Windows UTF-8 fixes; generateTexture + Canvas-2D validation checks; GDD coherence check; controls-audit + init-order rules in prompts. | Commit body lists each; rationale "code generation quality and runtime reliability". |
| Uncommitted | Add Steps 6-7: Vision verification (Playwright screenshot) and headless Playtest agent; gamification-science schema bundle (Octalysis/Hook/SDT/DDA, schemas.py:7-158); playwright+pillow deps; version 0.1.0 -> 0.2.0. | `git diff HEAD --stat` (graph.py +718, schemas.py +165, cli.py +24, pyproject.toml +8). Vision review itself is still a stub (graph.py:1380-1386). |

## Direction changes
- Model: Claude -> GPT-4o (768cb6b) -> gpt-5.2 (0ac1c5a) -> gpt-4.1 per aff76d2 body -> runtime default now `openrouter/free` via env vars (graph.py:46-50). Why aff76d2's stated gpt-4.1 config became an env-driven OpenRouter default: UNKNOWN (may relate to free-tier cost control; .env is gitignored).
- Framework: single node (962132f) -> full multi-stage graph with review loops (ae4bee0 onward).
- Code gen: single pass (8488f5f) -> 3-pass with best-of-N (aff76d2).
