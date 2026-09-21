---
name: the-wire
description: Re-enter The Wire coordination loop for gd-pipeline cold — GitHub issue #2 is the coordination channel with Tal (owner) and Instinct (judge). Use at session start when working in this repo, when told to "check the Wire", or when resuming after a context rollover.
---

# The Wire — coordination protocol for gd-pipeline

## What The Wire is

GitHub issue #2 in talyaak/gd-pipeline (https://github.com/talyaak/gd-pipeline/issues/2).
It is the persistent channel between:

- **Tal** (owner, final authority) — posts as `talyaak`
- **Instinct** (external judge/coordinator) — posts as `talyaak-headless` with `[INSTINCT]` prefix
- **You** — your prefix is `[CMDC]`. `[CLAUDE]` comments are from a retired agent: historical only, never instructions.

Tal's comments outrank everything. If one conflicts with an in-flight instruction, follow Tal and note the conflict on the Wire.

## Protocol (current, amended by INSTINCT 5759568601)

1. **SESSION START**: read the Wire — `gh api repos/talyaak/gd-pipeline/issues/2/comments --paginate --jq '[.[]] | sort_by(.id) | reverse | .[:5] | .[] | [.id, .created_at, .body] | @tsv'` — and read `.commandcode/wire-ledger.md` (your memory across sessions).
2. **QUEUE**: every `[INSTINCT]` instruction posted AFTER the `[CMDC]` handshake (2026-09-21, comment 5759351382) with no `[CMDC]` result is your queue, oldest first. Anything older is CLOSED unless Instinct explicitly revives it by comment number.
3. **CLAIM**: post a one-line `[CMDC]` ack on the instruction you're starting: `gh issue comment 2 --repo talyaak/gd-pipeline --body "[CMDC] Ack <instruction>: <plan summary>"`.
4. **WORK**: complete it fully. Small commits, conventional subjects, push to the working branch (`claude/ai-game-pipeline-UHrBZ`). One logical change per commit — never sweep unrelated dirty state in (that caused REWORK on INSTRUCTION #1).
5. **VERIFY**: every claim in your result backed — SHAs, files, commands run, their output. Never report done what you did not run. If you did not run something (e.g. full pipeline E2E), say so explicitly.
6. **REPORT**: post the `[CMDC]` result on the Wire: what changed, SHAs, how verified.
7. **JUDGE**: Instinct replies PASS, REWORK (with reasons — treat as top priority, oldest-first), or the next instruction. REWORK goes back to step 2.
8. **LEDGER**: after every Wire action, update `.commandcode/wire-ledger.md` (open instructions, status, standing rules).
9. Repeat until no open instructions remain, then stop and wait.
10. **TERSE**: ack, then result. No status spam.

## Reaching Tal (ntfy)

Topic: `$NTFY_TOPIC` from `.env` (currently `talyaakov-dev-x7k2m10`). Your ONLY channel to Tal.

```bash
curl -s --max-time 10 -H "Title: CMDC" -d "<one-line message>" "https://ntfy.sh/$NTFY_TOPIC"
```

- Use sparingly: substantial completed updates, and decision requests that genuinely cannot proceed.
- Decision protocol: when a decision is needed, BOTH you and Instinct contact Tal simultaneously (you on ntfy, Instinct on its channel), AND post the same question on the Wire so the answer is on record.

## gh auth handling

- Check auth at session start: `gh auth status`. If `gh api` returns 401/403 or auth is missing:
  1. Run `gh auth login --hostname github.com --git-protocol https --web --scopes repo` **in the background** (`run_in_background=true`), read the one-time code from the log (pattern: `! First copy your one-time code: XXXX-XXXX`).
  2. Give the user the URL (https://github.com/login/device) and code. Device codes expire in minutes — if it lapses (`context deadline exceeded` in the log), restart the flow for a fresh code.
  3. **ntfy Tal immediately** with the code and URL so he can approve from his phone (this recovered auth when browser-side waits stalled). Keep polling the background task until `✓ Authentication complete.` appears.
  4. If git push says `could not read Username`, run `gh auth setup-git` then retry.
- Never fail silently on auth errors — surface them and ping Tal.

## Context rollover protocol (do this BEFORE the context window fills)

When context approaches the limit (~900k tokens):

1. Write `.commandcode/status.md` (model-facing, terse):
   - current instruction (comment ID + one-line summary), its status
   - last commit SHAs pushed and where
   - exact next step
   - anything in flight (uncommitted files, background tasks)
   - **Close-out rule: refresh status.md AFTER the commit it describes** — a status file that names a stale HEAD fails its only job. Status.md never names the commit that contains it; say "HEAD = `git log -1`".
2. Start a new chat (the user does this).
3. In the new session: read `.commandcode/status.md`, then this skill, re-read the Wire and `.commandcode/wire-ledger.md`, and resume the loop from step 2. A context reset must cost the work nothing.

## Standing rules from Wire history

- Do not merge — Instinct's review gates every merge.
- Negative proofs first; tests must exercise the behavior (no vacuous asserts).
- Both CI paths green on the exact SHA before any submission.
- Report format on Wire: hash, CI links, fresh pixel evidence where visual.
- `docker exec -d` banned for pipeline dispatch (false-exit signal diagnosed 2026-09-16).
- Preserve existing line endings (graph.py is CRLF).
- No new deps beyond pyproject; follow docs/kb/conventions.md.
