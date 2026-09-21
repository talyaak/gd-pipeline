# Wire Ledger

Coordination channel: GitHub issue #2 (https://github.com/talyaak/gd-pipeline/issues/2).
My prefix: [CMDC]. Sources: [INSTINCT] = talyaak-headless (durable instructions), [CLAUDE] = retired agent (historical only), Tal = talyaak (outranks everything).
Read the Wire at session start and whenever told to check it.

## Protocol amendment (2026-09-21, INSTINCT 5759568601)

Only [INSTINCT] instructions posted AFTER the [CMDC] handshake (2026-09-21, 5759351382) are live.
All older instructions are CLOSED unless Instinct explicitly revives them by comment number.

## Open instructions

| Date | Comment ID | Source | Instruction | Status |
|------|-----------|--------|-------------|--------|
| 2026-09-21 | 5759336965 | [INSTINCT] | INSTRUCTION #1 - Gate repair: 1) wire real vision review (screenshot + 10-point checklist to VISION_MODEL, structured CodeReview, route on score); 2) live playtest telemetry + wire-or-remove rework path; 3) resolve verify_vision mixed edges. No behavior changes outside the three. | **PASS** (5760278663) — final SHAs: baseline 501d1cb + fixes 3d33b84 |
| 2026-09-21 | 5760279157 | [INSTINCT] | INSTRUCTION #2 - Self-continuity: the-wire skill (protocol, gh auth recovery w/ ntfy reauth, ledger resume) + context rollover protocol + first .commandcode/status.md. | **PASS WITH ONE FIX** (5760664965) — fix applied (aa665ed); formally CLOSED (5761050668) |
| 2026-09-21 | 5761662338 | [INSTINCT] | INSTRUCTION #3 - First end-to-end run through the repaired gates. | **PASS** (5762386730) |
| 2026-09-21 | 5762450855 | [INSTINCT] | INSTRUCTION #4 - APK-as-input Stage 0+2: video capture + spec-writer on 3-game eval set (Hay Day, Township, Family Farm Adventure). Branch feat/apk-input. Model seat amended to Qwen3-VL (5762635727). | **COMPLETE** — substance PASS + layout fix verified (5764930769, commit 23f446e). Ball with Tal: side-by-side eye-test vs 8/10 bar. NOTHING runs until his verdict |
| 2026-09-21 | 5765446332 | [INSTINCT] | INSTRUCTION #4 EXTENSION — spec-writer variance exam (Tal: free seat discarded, Qwen gets multiple runs): two more Qwen3-VL runs per video, same seat + same prompt, no tuning, to specs_qwen/run_2/ + specs_qwen/run_3/ (run_1 untouched). Spend estimate BEFORE firing; GOAT-credit routing checked first; report GOAT DeepSeek-vision seat (no run). | **RESULT POSTED** (5767415172, commit 0aa149b) — 6 Qwen specs, all parse. Awaiting Instinct gate |
| 2026-09-21 | 5767017517 | [INSTINCT] | INSTRUCTION #4 EXTENSION 2 — DeepSeek vision seat exam (un-parked): same 3 videos, SAME prompt/settings, seat deepseek/deepseek-v4-flash-vision-exp via GOAT credits (zero cash), output specs_deepseek/, seat+prompt recorded, spend estimate first. | **RESULT POSTED** (5767415172, commit 0aa149b) — 3 specs done. Awaiting Instinct gate |
| 2026-09-21 | 5767052184 | [INSTINCT] | RULING — Tal waives the human 8/10 eye-test for all seats. Eval is Instinct's gates alone (structural + cross-run consistency + plausibility). Recorded risk: knowledge-based, not footage-based. The Game bar (Tal's out-loud pass on a playable) is unaffected. | **NOTED** (in result 5767415172) |
| 2026-09-21 | 5766222886 | [INSTINCT] | Handoff CONFIRMED; report the runner model seat + tokens/cost if exposed (bakeoff: cost per passed gate). | **DONE** — runner seat meta/muse-spark-1.3-contributor; tokens/cost not exposed by this env |
| 2026-09-21 | 5767331910 | [INSTINCT] | INSTRUCTION — business-reference scrub: PATCH comment 5767052184 to the exact marker text (drop "before any studio outreach"); verify readback; one-line [CMDC] confirmation. | **DONE** (comment 5767434519) — scrub verified, phrase gone |
| 2026-09-21 | 5767647959 | [INSTINCT] | VERDICT — variance exam + DeepSeek seat (0aa149b): **PASS**. Record correction (commit msg said 1-element session_feel array; raw has 6). Production rulings: controls-section gesture caveat; Qwen3-VL stays incumbent, DeepSeek challenger pending schema-validation retry; headroom_retrieve injection logged as known gateway behavior. **INSTRUCTION #4 + both extensions COMPLETE.** Next: #5 (Nemotron GEN_MODEL) when Tal says go. | **CORRECTION POSTED** (5767717961) — join byte-verified faithful; gated SHA not amended |

## Open work after the exam

- Await Instinct's gate on the 9 new specs (0aa149b).
- Queued: INSTRUCTION #5 (Nemotron 3 Ultra as GEN_MODEL on the main pipeline) — not yet posted as a full instruction; wait for the Wire.
- Local runner scripts (/tmp/opencode/run_deepseek.py, variance_run.py, wire_listen.sh) are not committed; the DeepSeek tool_choice=none mechanism is documented in the commit message + result comment.

## Runner transition (2026-09-21, INSTINCT 5765806783)

- cmdc CLI retired; OpenCode agent holds the [CMDC] seat. Same prefixes, gates, spend rule, re-read rule.
- Handoff AGENTS.md @ fa9443b PASS (5765939549) with one trip hazard: skill + ledger were NOT mirrored — carried to feat/apk-input at catch-up instead. This ledger is now the live copy on feat/apk-input.

## Closed / historical

- 2026-09-15 5685812737 (helper-depth/inventory round): CLOSED by ruling 5759568601 — pre-handshake. Harness files live on the gh-pages branch; work not in queue.
- 2026-09-16 5693094361, 5693248016, 5693467942: CLOSED by ruling 5759568601 — pre-handshake.
- 2026-09-15: real-device defects round on 3cb06b1 — 51d2163 FAIL, 7a463ae PASS -> merged as 3cb06b1.
- 2026-09-15: z-order/contrast round — cf78f9c FAIL (vacuous tests) -> 95c5805 PASS -> merged as 18a0086.
- 2026-09-15: Part 2b closed; fly-coin-on-collect wording dropped.
- 2026-09-17..18: farm_idle test-split/trim/rehab work (Claude era) — historical.

## Standing rules from Wire history

- Do not merge — Instinct's review gates every merge.
- Negative proofs first; tests must exercise the behavior (no vacuous asserts).
- Both CI paths green on the exact SHA before any submission.
- Report format on Wire: hash, CI links, fresh pixel evidence where visual.
- `docker exec -d` banned for pipeline dispatch (false-exit signal diagnosed 2026-09-16).
