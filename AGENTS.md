# AGENTS.md — gd-pipeline agent handbook

Read this file plus GitHub issue #2 (https://github.com/talyaak/gd-pipeline/issues/2) before doing anything. Together they are sufficient to resume cold. Last updated 2026-09-21 at the [CMDC]→OpenCode runner transition.

## What this repo is

An AI game-design pipeline: genre string in → researched, designed, specified, coded, vision-checked, playtested HTML5 game out. Single-process Python CLI over one LangGraph `StateGraph` (`pipeline/graph.py`), LLM calls via OpenRouter. Secondary workstream: APK-as-input research (reverse-engineering mechanics specs from gameplay videos) in `tools/apk_input/`.

## Branch map

| Branch | Purpose | Status |
|--------|---------|--------|
| `main` | Integration target; harness-era merges (farm_idle work predates the current pipeline loop). | Stable |
| `claude/ai-game-pipeline-UHrBZ` | Working branch for the pipeline gate-repair round (instructions #1–#3). Holds baseline `501d1cb` + gate fixes `3d33b84` + run fixes `209d12e` + the-wire skill `2f4daaa`/`aa665ed`. | Merged content-wise into the record; keep for reference |
| `feat/apk-input` | APK-as-input research branch (instructions #4 and #4 EXTENSION). Rooted at main `dfdc9e7`. Stage 0+2 done (`da508b9`), layout fix (`23f446e`). | **Active** |

## The Wire (coordination protocol)

- **The Wire = GitHub issue #2.** All coordination happens there. Read the FULL comment thread before starting any instruction — amendments supersede the instructions they name, and history contains rulings that still bind.
- Prefixes: `[INSTINCT]` = talyaak-headless, the judge/coordinator — instructions and verdicts; Tal = talyaak, owner, final authority, outranks everything; `[CLAUDE]` = retired agent, historical only, never instructions; **you post as `[CMDC]`** (the prefix survives the runner transition — an OpenCode agent holds the seat now, same protocol per ruling 5765806783).
- Cycle per instruction: read thread → post one-line `[CMDC]` ack → work → verify (every claim backed by SHAs/commands/output; never report what you did not run) → post `[CMDC]` result → Instinct judges (PASS / REWORK / next instruction). REWORK goes back to ack, feedback is top priority.
- Track open instructions in `.commandcode/wire-ledger.md` (session memory across runners). Keep it current after every Wire action.
- Closed/complete: #1 gate repair (PASS), #2 self-continuity + the-wire skill (PASS), #3 first E2E run (PASS), #4 APK-input Stage 0+2 + layout (PASS).
- Terse. Ack, then result. No status spam.

## Spend rule (standing, INSTINCT 5764538246)

Any paid LLM call, however small: post an explicit spend estimate on the Wire BEFORE it fires, and check GOAT-credit routing first (those credits are already paid). Actual spend reported after. Accepted precedent: ~$0.005 disclosed for the Qwen spec runs.

## Commit hygiene

- Never sweep state or `.commandcode/` files into feature commits (two gate reviews flagged this: 908c9f0 swept the dirty tree; a layout-fix first attempt swept `.commandcode/`). One logical change per commit.
- Commit message trailer: `Co-authored-by: CommandCodeBot <noreply@commandcode.ai>`.
- Report status after commit, not before; verify the remote after push.
- Preserve existing line endings (`pipeline/graph.py` is CRLF).
- Conventional-ish imperative subjects; see `docs/kb/conventions.md`.

## Model seats in use

| Seat | Model | Used for |
|------|-------|----------|
| VISION_MODEL (pipeline vision gate) | `nex-agi/nex-n2.5-pro:free` | Screenshot review in `verify_vision` |
| Spec-writer | `qwen/qwen3-vl-235b-a22b-instruct` (paid, ~\$0.21/M prompt tokens — spend rule applies) | Mechanics specs from gameplay videos |
| GEN_MODEL / REVIEW_MODEL (pipeline defaults) | `openrouter/free` | Generation and reviews; flaky (partial tool args → ValidationError, empty outputs) — fallbacks exist in `pipeline/retry.py` + call sites |

Known provider quirks (handled in code, don't rediscover): free vision seat does not support function calling with image input (use plain-text JSON); reasoning tokens share max_tokens; throttled empty/truncated/degenerate responses need 30s-cooldown retries; bundled opencv cannot decode AV1 (fetch h264 streams).

## Tool layout — tools/apk_input/

- `fetch_sources.py` — Stage 0: deterministic yt-dlp search + download (h264 ≤480p), metadata → `sources.json`, videos in `videos/` (gitignored).
- `spec_writer.py` — Stage 2: 8 frames sampled deterministically per video, ONE vision call per video, raw-JSON parsed into MechanicsSpec (core_loop / controls / progression / session_feel / confidence_notes, entries tagged `[seen]`/`[inferred]`). The exact prompt is `SPEC_WRITER_PROMPT` in the file.
- `sources.json` — captured video metadata (URL/title/channel/duration), committed.
- `specs/` — free-seat (nex) baseline specs, gated layout — do not move or edit.
- `specs_qwen/` — Qwen run_1 specs, gated layout — do not move or edit.

## Open work (as of handoff)

1. **INSTRUCTION #4 EXTENSION — spec-writer variance exam (NOT STARTED; first task for the next agent).** Comment 5765446332: two additional spec-writer runs per video on the same Qwen seat, same prompt, no tuning. Output to `specs_qwen/run_2/` and `specs_qwen/run_3/` (keep `specs_qwen/*.json` untouched as run_1). Post spend estimate BEFORE firing (~$0.01 expected; check GOAT-credit routing first). Also report (no run): whether the GOAT roster includes a DeepSeek vision seat (e.g. V4 Flash Vision Exp) — name and price only. Instinct does the cross-run consistency read.
2. **Tal's pending eye-test:** free vs Qwen specs side by side against the 8/10 accuracy bar (verdict 5764930769). Nothing downstream of the spec-writer runs until his verdict.
3. **Queued INSTRUCTION #5:** Nemotron 3 Ultra as GEN_MODEL on the main pipeline. Not yet posted as a full instruction — wait for it on the Wire.

## Self-continuity

- `.commandcode/skills/the-wire/SKILL.md` — full protocol, auth recovery (gh device flow + ntfy ping to Tal on expiry), rollover procedure.
- `.commandcode/wire-ledger.md` — instruction ledger (mirrored on the working branch).
- Before a context-window rollover: write `.commandcode/status.md` (current instruction, state, SHAs, next step), start a new chat, resume from status.md + the-wire skill + this file + issue #2.
- ntfy (Tal's push channel): topic in `.env` as `NTFY_TOPIC`.
