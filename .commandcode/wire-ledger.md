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
| 2026-09-21 | 5759336965 | [INSTINCT] | INSTRUCTION #1 - Gate repair: 1) wire real vision review (screenshot + 10-point checklist to VISION_MODEL, structured CodeReview, route on score); 2) live playtest telemetry + wire-or-remove rework path; 3) resolve verify_vision mixed edges. No behavior changes outside the three. | RESULT POSTED 2026-09-21 — commit 908c9f0 on claude/ai-game-pipeline-UHrBZ, awaiting gate review |

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
