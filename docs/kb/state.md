# Current State

As of 2026-09-21, branch `claude/ai-game-pipeline-UHrBZ`, HEAD aff76d2, working tree dirty.

## Branches
- `main` (local): 9c6eeb3 "first commit" — behind origin/main.
- `origin/main`: ff91386, merge of PR #1 — includes history up to c6acacb but NOT aff76d2. Source: `git log --all --graph`.
- `claude/ai-game-pipeline-UHrBZ` (current): aff76d2 + uncommitted changes; also tracked at origin but at c6acacb.
- UNKNOWN: why aff76d2 (authored 2026-02-28) was excluded from the PR merged 2026-04-12 — possibly intentional WIP exclusion or merge taken before push; no record in the tree.

## Uncommitted work (git status / git diff HEAD)
- Modified: `pipeline/cli.py` (+24), `pipeline/graph.py` (+718), `pipeline/schemas.py` (+165), `pyproject.toml` (+8: playwright, pillow, version 0.2.0, setuptools package config).
- Content: vision verification + playtest nodes, gamification schema bundle — Steps 6-7 are uncommitted and incomplete (see below).
- Untracked: `.commandcode/` (this tooling's own dir), plus `docs/kb/` (this KB).

## Open TODOs in code
- pipeline/graph.py:1377 — "TODO: Implement proper vision structured output when langchain supports it" — the only TODO marker in the repo. Vision review currently returns a hardcoded pass (graph.py:1380-1386).

## Unfinished / inconsistent work visible in the tree
- Vision gate is a stub (passes without reviewing) — graph.py:1372-1386.
- Playtest telemetry never increments `score`/`actions`; metrics permanently 0 — graph.py:1459-1491.
- `should_rework_playtest` reads `playtest_review`, never present in `PipelineState`; playtest loop is dead code — graph.py:1594-1600.
- `verify_vision` has both a fixed edge to `run_playtest` and conditional edges — ambiguous wiring — graph.py:1673-1674.
- `MAX_IMPL_SPEC_ATTEMPTS` (graph.py:89) and `MAX_PLAYTEST_ATTEMPTS` (graph.py:92) are defined but never enforced.
- `.env.example` still documents `OPENAI_API_KEY`; code reads `OPENROUTER_API_KEY` (graph.py:81).
- Hardcoded fallback GDD is an endless runner regardless of genre — graph.py:259-309.
- Output dir named `--help_20260823_053431/` exists in `output/` — the CLI help path was invoked in a way that treated `--help` as a genre at least once (cli.py:191-196 handles bare `--help`; cause UNKNOWN).
- `output/gdd_draft.json` at output root is a leftover from the pre-run-dir era (bfa083e wrote there; current code writes into run dirs).

## Testing / CI
- No tests exist despite pytest+ruff in dev deps (pyproject.toml:18-21). No CI/workflow config. Nothing in the repo runs automatically; `python -m pipeline` is exercised manually (39 run dirs under `output/` attest).

## Run history
- 39 run dirs total: 37 `endless_runner_*` runs (2026-02-27 -> 2026-08-23), 1 `vampire_survivors_style_bullet_heaven_*` run, 1 bogus `--help_*` run (read_directory output/).
- The latest full-structure run (vampire bullet heaven) stopped after `02_gdd` — .checkpoint.sqlite present, no `03_impl_spec/` — an abandoned/interrupted run.

## Docs
- README.md is a one-line stub (`# gd-pipeline`); this KB under docs/kb/ is the only real documentation.
