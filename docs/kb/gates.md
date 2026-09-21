# Quality Gates

All gates pass on score >= 7 (LLM-judged) or issue-count thresholds (static). Every review is persisted to the run dir (`output/<step>/attempt_N/review.json`).

| Gate | Where | Checks | Pass | Fail path | Runner |
|------|-------|--------|------|-----------|--------|
| GDD auto-review | graph.py:369-412 (`review_gdd`) | Weighted rubric (specificity 3x, core loop 2x, scope 2x, fun 2x, juice 1x) + design-coherence check: N lanes need N-1 lateral inputs, every mechanic needs a control (graph.py:346-353) | score >= 7 | -> `generate_gdd` rework (max 3, graph.py:88) -> forced to HITL | REVIEW_MODEL LLM; heuristic fallback if None (graph.py:384-405) |
| GDD human gate (HITL) | graph.py:433-465 + cli.py:41-92 | Human judgment of full GDD | "approve" | free-text or "fix" -> rework with feedback as top-priority input | Human via CLI (LangGraph interrupt) |
| Impl spec auto-review | graph.py:669-717 (`review_impl_spec`) | MVP-lenient rubric: entity completeness 2x, balance 2x, buildability 2x, state machine 1x, assets 1x | score >= 7 | -> `human_review_impl_spec` (NO auto-retry, graph.py:720-725) | REVIEW_MODEL LLM; heuristic fallback (graph.py:687-708) |
| Impl spec human gate (HITL) | graph.py:731-758 + cli.py:95-142 | Human judgment | "approve" | feedback -> one targeted rework (graph.py:731-736 docstring) | Human via CLI |
| Static validation gate | validate.py:33-110, enforced in review_code graph.py:1194-1214 | HTML/JS structure, banned dt names, external asset refs, `this.load.*`, node --check syntax, Phaser.Game/Scene/update presence, generateTexture presence, Canvas-2D-on-Graphics methods | 0 issues | >5 issues: score 2, LLM review skipped entirely (graph.py:1197-1201); 1-5 issues: score 3, LLM review skipped (graph.py:1203-1214) | Pure Python + Node.js if on PATH (validate.py:113-139) |
| Code auto-review | graph.py:1185-1258 (`review_code`) | Rubric: runtime correctness 4x, core loop 3x, juice 2x, spec fidelity 1x + controls audit + init-order check (graph.py:1131-1182) | score >= 7 | -> `generate_code` rework (max 3, graph.py:90) then forced on to vision | REVIEW_MODEL LLM; heuristic fallback (graph.py:1234-1250) |
| Vision gate (STUB) | graph.py:1314-1395 (`verify_vision`) | Screenshot capture via Playwright only; the 10-point visual checklist (graph.py:1292-1311) is NOT evaluated — hardcoded passing 7/10 review (graph.py:1380-1386), TODO graph.py:1377 | screenshot success | Playwright exception -> score 1 -> may loop to code gen (max 2, graph.py:1406-1409) | Playwright; no model |
| Playtest gate (ADVISORY) | graph.py:1444-1600 (`run_playtest`) | 30s headless session: crash count, fps, survival, score/actions (always 0 — telemetry never increments them, graph.py:1459-1491) | N/A — always ends graph (graph.py:1600) | none; `should_rework_playtest` is dead code reading a never-set state key (graph.py:1596) | Playwright + REVIEW_MODEL analysis |

## Cross-cutting gate mechanics

- "FORCED" progression: after max attempts at any stage the pipeline continues rather than aborts (GDD -> HITL graph.py:423-425; code -> vision graph.py:1269-1271; vision -> playtest graph.py:1406-1407). CLI displays failed stages as "FORCED" (cli.py:329-338).
- Best-of-N inside `generate_code`: intermediate passes kept only if they have fewer validation issues than the successor (graph.py:1088-1110).
- Token economy: validation gate exists specifically to skip LLM review on broken code (cdff53b, graph.py:1194 comment); impl spec skips auto-rework loops (bc8561f-era design, enforced graph.py:720-725).
