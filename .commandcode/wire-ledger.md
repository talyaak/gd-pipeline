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
| 2026-09-21 | 5761662338 | [INSTINCT] | INSTRUCTION #3 - First end-to-end run through the repaired gates. VISION_MODEL set, one genre, act as human at HITL. Deliver run dir, artifact, all reviews, screenshot, telemetry. Failures are valid results. | **PASS** (5762386730) — fixes 209d12e gated |
| 2026-09-21 | 5762450855 | [INSTINCT] | INSTRUCTION #4 - APK-as-input Stage 0+2 on feat/apk-input (rooted main dfdc9e7). Qwen seat amendment 5762635727. | **COMPLETE** (5764930769) — work on feat/apk-input, commits da508b9/243f669 + layout 23f446e |
| 2026-09-21 | 5765446332 | [INSTINCT] | INSTRUCTION #4 EXTENSION — variance exam: 2 more Qwen runs/video to specs_qwen/run_2, run_3. | **PASS** (5767647959) — commit 0aa149b |
| 2026-09-21 | 5767017517 | [INSTINCT] | INSTRUCTION #4 EXTENSION 2 — DeepSeek vision seat exam via GOAT credits. | **PASS** (5767647959) — commit 0aa149b |
| 2026-09-21 | 5767052184 | [INSTINCT] | RULING — eye-test waived; business scrub 5767331910 DONE. | NOTED |
| 2026-09-22 | 5767735741 | [INSTINCT] | INSTRUCTION #5 - GEN_MODEL swap to Nemo (nvidia/nemotron-3-ultra-550b-a55b, Command Code seat, Tal green-lit) + full pipeline rerun. Spend estimate BEFORE firing. Exam artifacts untouched. | **RESULT POSTED** (5771228660) — routing 13381d7; run hyper-casual_runner_20260922_042253 exit-0 honest FAILURE (GDD 8/10, spec 4/10, code 3/10×5, vision/playtest env-blocked). Awaiting gate |
| 2026-09-22 | 5771312475 | [INSTINCT] | AMENDMENT to #5 — fire DeepSeek/GLM generation on GOAT credits, Tal-approved spend. | **HELD** by 5771363361 — Nemo result points at validator, do not fire |
| 2026-09-22 | 5771371644 | [INSTINCT] | INSTRUCTION #6 — read-only investigation static Empty-script check vs Nemo artifacts. | **PASS** (5771759515) |
| 2026-09-22 | 5771441941 | [INSTINCT] | ENV UPDATE — Chromium blocker RESOLVED. | NOTED |
| 2026-09-22 | 5771759515 | [INSTINCT] | INSTRUCTION #7 — cap fix + truncation self-diagnosis + CDN check. Code only. | **RESULT POSTED** (5777800976) — 7584c0a: both seats 65_536 (providers.json + live probe); seat pick deepseek-v4-pro; 4-shape repro green; CRLF kept |
| 2026-09-22 | 5771816954 | [INSTINCT] | REQUEST from Tal — usage stats (GOAT credits, allowance, per-seat). | **RESULT POSTED** (5775691687) — OR lifetime \$10.01/mo \$0.21; GOAT meter server-side only (no local endpoint); per-seat from cost log (313 entries, 1M/2.3M toks) |
| 2026-09-23 | 5790428497 | [INSTINCT] | RULING: option (a) — add deepseek-v4-pro to HEADROOM_MODELS, probe, refire. | **MISFIRE #2** (5792231680/5792243847) — seat rejects tool_choice bind in thinking mode (400 x2 at GDD). BLOCKED report posted; probe matrix proposed |
| 2026-09-23 | 5792115460 | [INSTINCT] | Status check on refired E2E (2h+, no report). | **ANSWERED** (5792231680) — alive, run dead, interim posted |

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
