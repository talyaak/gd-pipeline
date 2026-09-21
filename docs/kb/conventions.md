# Conventions

## Code style (observed in pipeline/*.py)
- Module docstring at top of every non-empty file describing purpose; `pipeline/graph.py` opens with a numbered step summary (graph.py:1-13). `pipeline/__init__.py` is empty.
- Section banner comments: `# ─── Node: name ────────` and `# ====` separators (graph.py:95, 121, 157, 768, 1128; schemas.py:7, 360, 510, 533).
- Type hints throughout; `X | None` union syntax (requires Python >= 3.11, pyproject.toml:5).
- TypedDict for graph state, Pydantic BaseModel for all LLM I/O — strict separation (graph.py:98 vs schemas.py).
- Prompts live as module-level constants next to their node function, in uppercase (`GDD_PROMPT`, `REWORK_CODE_PROMPT`); heavy use of `**bold**` Markdown inside prompts; `\`-continued strings (graph.py:124-138 etc.).
- Constants for loop limits: `MAX_<STAGE>_ATTEMPTS` (graph.py:88-92).
- Output-token discipline: every LLM call sets an explicit `max_tokens` via `_max_tokens()` cap table (graph.py:53-71); review prompts demand conciseness (e.g. "under 400 tokens", graph.py:321-322).
- Temperature convention: generation 0.3-0.7, review 0.3 (graph.py:143, 231, 371, 591, 671, 1057, 1217).
- Fallback pattern: every structured LLM call site has an `if result is None:` heuristic fallback so a non-function-calling model never crashes the run (graph.py:259, 384, 687, 1234).
- Windows-safe I/O: explicit `encoding="utf-8"` on `write_text`/`read_text` (output.py:75, 93; cli.py:162) — added in aff76d2; one uncommitted call site omits it (graph.py:1558).
- No comments beyond structural banners and non-obvious rationale; no linter config beyond ruff declared as dev dep (pyproject.toml:20).

## Naming
- Nodes/functions: snake_case verbs (`generate_gdd`, `review_code`, `should_rework_*` for conditional edges).
- Schemas: PascalCase matching the artifact (`GameDesignDocument`, `ImplSpecReview`); review models share the `passed/score/strengths/issues/suggestions` shape.
- Run artifacts: zero-padded step dirs `01_genre_research` ... `06_playtest` with `attempt_N` subfolders (output.py:6-22); env vars `GEN_MODEL`/`REVIEW_MODEL`/`VISION_MODEL`.

## Git / commit conventions (from `git log --all`)
- Conventional-ish imperative subjects describing the change, often with a detailed bullet body ("Overhaul code generation quality and runtime reliability", aff76d2).
- Authorship: `Claude` for agent-authored commits (with `Co-Authored-By: Claude ...` trailer, e.g. aff76d2), `talyaak` for manual commits ("some manual work towards quality improvement", e0a6895).
- Branch naming: `claude/ai-game-pipeline-UHrBZ` (agent-generated work branch); merged to main via GitHub PR ("Merge pull request #1", ff91386).
- Commit granularity: one feature/step per commit, in pipeline-step order (see decisions.md).

## CLI conventions
- `python -m pipeline` as the only interface; argparse-free manual `sys.argv` parsing (cli.py:190-217); flag style `--resume`, `--inject-code`.
- Console output: bracketed node tags `[generate_code]`, `->` artifact paths via `output.rel()`, boxed summary blocks with `=`/`-` separators.
