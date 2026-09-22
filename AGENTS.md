# AGENTS.md — gd-pipeline agent handbook

Read this file plus GitHub issue #2 (https://github.com/talyaak/gd-pipeline/issues/2) before doing anything. Together they are sufficient to resume cold. Last updated 2026-09-22 after the [CMDC]→OpenCode runner session: #4 EXTENSION + EXTENSION 2 done and PASSed, #5 posted by Instinct (UNACKED — your first act if inbound).

## What this repo is

An AI game-design pipeline: genre string in → researched, designed, specified, coded, vision-checked, playtested HTML5 game out. Single-process Python CLI over one LangGraph `StateGraph` (`pipeline/graph.py`), LLM calls via OpenRouter. Secondary workstream: APK-as-input research (reverse-engineering mechanics specs from gameplay videos) in `tools/apk_input/`.

## Branch map

| Branch | Purpose | Status |
|--------|---------|--------|
| `main` | Integration target; harness-era merges (farm_idle work predates the current pipeline loop). | Stable |
| `claude/ai-game-pipeline-UHrBZ` | Working branch for the pipeline gate-repair round (instructions #1–#3). Holds baseline `501d1cb` + gate fixes `3d33b84` + run fixes `209d12e` + the-wire skill `2f4daaa`/`aa665ed`. | Merged content-wise into the record; keep for reference |
| `feat/apk-input` | APK-as-input research branch (instructions #4, #4 EXTENSION, EXTENSION 2, plus ledger/continuity commits). Rooted at main `dfdc9e7`. Stage 0+2 (`da508b9`→`243f669`), layout fix (`23f446e`), variance exam (`0aa149b`), continuity/ledger `3c61e49`→`22bdea0`. | **Active; Instinct says do not touch exam artifacts or rewrite 0aa149b** |

## The Wire (coordination protocol)

- **The Wire = GitHub issue #2.** All coordination happens there. Read the FULL comment thread before starting any instruction — amendments supersede the instructions they name, and history contains rulings that still bind.
- Prefixes: `[INSTINCT]` = talyaak-headless, the judge/coordinator — instructions and verdicts; Tal = talyaak, owner, final authority, outranks everything; `[CLAUDE]` = retired agent, historical only, never instructions; **you post as `[CMDC]`** (the prefix survives the runner transition — an OpenCode agent holds the seat now, same protocol per ruling 5765806783).
- Cycle per instruction: read thread → post one-line `[CMDC]` ack → work → verify (every claim backed by SHAs/commands/output; never report what you did not run) → post `[CMDC]` result → Instinct judges (PASS / REWORK / next instruction). REWORK goes back to ack, feedback is top priority.
- Track open instructions in `.commandcode/wire-ledger.md` (session memory across runners, now the live copy on feat/apk-input). Keep it current after every Wire action.
- Closed/complete: #1 gate repair (PASS), #2 self-continuity + the-wire skill (PASS), #3 first E2E run (PASS), #4 APK-input Stage 0+2 + layout (PASS), #4 EXTENSION variance exam (PASS — `0aa149b`, report 5767415172), #4 EXTENSION 2 DeepSeek seat (PASS, same SHA/report). Awaiting Instinct gate on #5 only.
- A business-reference scrub (comment 5767331910: PATCH 5767052184's body, drop "before any studio outreach") is DONE (confirmed 5767434519). Do not re-scrub gated history.
- Terse. Ack, then result. No status spam.

## Spend rule (standing, INSTINCT 5764538246)

Any paid LLM call, however small: post an explicit spend estimate on the Wire BEFORE it fires, and check GOAT-credit routing first (those credits are already paid). Actual spend reported after. Accepted precedent: ~$0.005 disclosed for the Qwen spec runs.

## Commit hygiene

- Never sweep state or `.commandcode/` files into feature commits (two gate reviews flagged this: 908c9f0 swept the dirty tree; a layout-fix first attempt swept `.commandcode/`). One logical change per commit.
- Commit message trailer: `Co-authored-by: CommandCodeBot <noreply@commandcode.ai>`.
- Report status after commit, not before; verify the remote after push.
- Preserve existing line endings (`pipeline/graph.py` is CRLF).
- Conventional-ish imperative subjects; see `docs/kb/conventions.md`.

## Model seats in use (exam verdict 5767647959 + #5 instruction 5767735741)

| Seat | Model | Used for |
|------|-------|----------|
| VISION_MODEL (pipeline vision gate) | `nex-agi/nex-n2.5-pro:free` | Screenshot review in `verify_vision` |
| Spec-writer (incumbent, schema-clean) | `qwen/qwen3-vl-235b-a22b-instruct` (paid, ~$0.21/M prompt tokens — spend rule applies) | Mechanics specs from gameplay videos |
| DeepSeek challenger (richer, schema-sloppy) | `deepseek/deepseek-v4-flash-vision-exp` (GOAT $20 allowance; $0.15/M in, $0.60/M out off-peak) via the Command Code headroom proxy | Seat comparison only; becomes challenger only if a future sweep adds a schema-validation retry |
| GEN_MODEL (INSTRUCTION #5 — UNACKED, start here) | `nvidia/nemotron-3-ultra-550b-a55b` on the Command Code seat | **Posted 5767735741 (Tal green-lit): swap GEN_MODEL to Nemo + full pipeline rerun. Cost estimate on the Wire BEFORE firing.** |
| GEN_MODEL / REVIEW_MODEL (pipeline defaults) | `openrouter/free` | Generation and reviews; flaky (partial tool args → ValidationError, empty outputs) — fallbacks exist in `pipeline/retry.py` + call sites |

Known provider quirks (handled in code, don't rediscover): free vision seat does not support function calling with image input (use plain-text JSON); reasoning tokens share max_tokens; throttled empty/truncated/degenerate responses need 30s-cooldown retries; bundled opencv cannot decode AV1 (fetch h264 streams).
**Gateway quirk (logged as known behavior per verdict): the Command Code headroom proxy injects a `headroom_retrieve` tool; without `tool_choice="none"` the model returns `finish_reason=tool_calls` with empty text.**

## Tool layout — tools/apk_input/

- `fetch_sources.py` — Stage 0: deterministic yt-dlp search + download (h264 ≤480p), metadata → `sources.json`, videos in `videos/` (gitignored).
- `spec_writer.py` — Stage 2: 8 frames sampled deterministically per video, ONE vision call per video, raw-JSON parsed into MechanicsSpec (core_loop / controls / progression / session_feel / confidence_notes, entries tagged `[seen]`/`[inferred]`). The exact prompt is `SPEC_WRITER_PROMPT` in the file.
- `sources.json` — captured video metadata (URL/title/channel/duration), committed.
- `specs/` — free-seat (nex) baseline specs, gated layout — do not move or edit.
- `specs_qwen/` — Qwen run_1 specs (gated) + `run_2/` + `run_3/` variance specs — all gated, do not move or edit.
- `specs_deepseek/` — DeepSeek seat specs (gated), incl. `family_farm_adventure_spec.raw_session_feel.txt` (raw array; the committed JSON's `session_feel` is the faithful join — see correction comment 5767717961, never amend `0aa149b`).
- Standing controls caveat (verdict): adapters must NOT treat drag/hold gesture claims from specs as ground truth — 8 sampled frames cannot show a gesture.

## Open work (as of 2026-09-22 — inbound agent starts here)

1. **INSTRUCTION #5 — Nemotron 3 Ultra as GEN_MODEL + full pipeline rerun (UNACKED).** Comment 5767735741. Constraints: spend estimate BEFORE firing; spec-writer stays Qwen; do not touch exam artifacts or rewrite `0aa149b` history (the session_feel correction lives in 5767717961, not a force-push). Acceptance: run completes end to end; report with commit hash, green CI, explicit "not verified" list; Instinct gates after.
2. **Eye-test:** WAIVED by Tal for all seats (ruling 5767052184, business-scrubbed). No human 8/10 test. Tal's personal pass on a playable remains the final Game gate (not this pipeline's).
3. **Runner seat for the bakeoff:** report model seat + tokens/cost if exposed (cost per passed gate). The OpenCode session ran `meta/muse-spark-1.3-contributor`; tokens/cost were not exposed in that environment — still an open ask for the next runner.

## Self-continuity

- `.commandcode/skills/the-wire/SKILL.md` — full protocol, auth recovery (gh device flow + ntfy ping to Tal on expiry), rollover procedure.
- `.commandcode/wire-ledger.md` — instruction ledger (carried to feat/apk-input at the [CMDC]→OpenCode handoff; full history also on claude/ai-game-pipeline-UHrBZ).
- Before a context-window rollover: write `.commandcode/status.md` (current instruction, state, SHAs, next step), start a new chat, resume from status.md + the-wire skill + this file + issue #2.
- ntfy (Tal's push channel): topic in `.env` as `NTFY_TOPIC`.
