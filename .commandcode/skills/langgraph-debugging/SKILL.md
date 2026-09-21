---
name: langgraph-debugging
description: Debug LangGraph/LangChain pipelines — sync vs async nodes, LLM response parsing, checkpoint/SQLite timeout diagnosis, and test fixture or mock signature mismatches. Use when LangGraph node tests hang, structured output parsing fails, or a node reports failed_max_attempts without a clear error.
license: MIT
metadata:
  version: "1.0.0"
  origin: "migrated from Hermes agent (gd-gpt)"
---

# LangGraph/LangChain Pipeline Debugging

## Overview

Common patterns and fixes when debugging LangGraph-based LLM pipelines. These issues appear repeatedly across projects using LangGraph + LangChain for multi-agent workflows.

## When to Use

- Debugging test failures in LangGraph pipelines
- LLM response parsing errors
- Async/sync node function issues
- Browser-based execution validation failures
- Mock signature mismatches in tests

---

## Pattern 1: LangGraph Nodes Must Be Synchronous

**Symptom:** Tests hang, timeout, or fail with cryptic errors when using `async def` node functions.

**Root Cause:** LangGraph's `StateGraph` expects synchronous node functions. Async nodes are not awaited properly by the graph executor.

**Fix:** Convert async node functions to synchronous:

```python
# WRONG - async def
async def variant_gen(state: RunState) -> dict:
    report = await async_run_execution_report(html, out_dir)

# CORRECT - def (sync)
def variant_gen(state: RunState) -> dict:
    report = run_execution_report(html, out_dir)  # sync version
```

**Verification:**
```bash
pytest tests/test_pipeline_integration.py -v
```

---

## Pattern 2: LLM Response Objects Have `.content` Attribute

**Symptom:** `'types.SimpleNamespace' object has no attribute 'find'` or similar attribute errors when parsing LLM responses.

**Root Cause:** LangChain LLM `invoke()` returns a message object (e.g., `BaseMessage`, `SimpleNamespace`) with a `.content` attribute, not a raw string.

**Fix:** Extract content before string operations:

```python
# WRONG - assumes raw is a string
raw = invoke_with_retry(lambda: llm.invoke(prompt))
start = raw.find("{")  # AttributeError!

# CORRECT - handle message objects
raw = invoke_with_retry(lambda: llm.invoke(prompt))
raw_content = raw.content if hasattr(raw, "content") else str(raw)
start = raw_content.find("{")
```

**Rule:** Always check for `.content` attribute when processing LLM responses.

---

## Pattern 3: Test Fixtures Must Match Semantic Validation

**Symptom:** Browser execution tests pass but semantic validation fails with "no active gameplay scene" or similar.

**Root Cause:** Validators check for specific patterns (scene name, score registry updates) to detect active gameplay.

**Fix:** Update test fixtures to match validator expectations:

```html
<!-- Scene name must be "PlayScene" for semantic validation -->
class PlayScene extends Phaser.Scene {
    update(time, delta) {
        // Must increment score to indicate active gameplay
        const game = this.scene.systems.game;
        if (game.registry.has('score')) {
            game.registry.inc('score', 1);
        }
    }
}
```

**Verification:**
```bash
pytest tests/test_execute.py::test_known_good_game_loads_clean -v
```

---

## Pattern 4: Mock Functions Must Match Call Signatures

**Symptom:** `TypeError` when monkeypatching LLM factory functions.

**Root Cause:** Factory functions like `get_review_llm(node="review")` expect a `node` parameter.

**Fix:** Update mock lambdas to accept the parameter:

```python
# WRONG
monkeypatch.setattr("pipeline.nodes.review.get_review_llm", lambda: _FakeLLM(...))

# CORRECT
monkeypatch.setattr("pipeline.nodes.review.get_review_llm", lambda node: _FakeLLM(...))
```

---

## Pattern 5: Tight Debugging Loop

**Command patterns for rapid iteration:**

```bash
# Single failing test
pytest tests/test_review.py::test_valid_review_response_still_passes -v

# Related test group
pytest tests/test_human_review.py tests/test_pipeline_integration.py -v

# Full suite after fix
pytest tests/ -q

# Flaky browser tests - run multiple times
for i in {1..5}; do pytest tests/test_execute.py -v || break; done
```

---

## Pattern 6: Common Validation Failure Quick Reference

| Validator Error | Likely Cause | Fix |
|----------------|--------------|-----|
| "no active gameplay scene" | Scene not named PlayScene, or no score increment | Rename scene, add `registry.inc('score')` |
| "window.__GAME__ not exposed" | Game not assigned to `window.__GAME__` | Add `window.__GAME__ = game` |
| "asset reference is flagged" | External asset URL in HTML | Use generated textures instead |
| "banned delta_time name" | Variable named `deltaTime` | Use `delta` instead |

---

## Pattern 7: Node Timeout Diagnosis via Checkpoint Inspection

When a LangGraph pipeline fails with `failed_max_attempts` but no clear error in logs, inspect the SQLite checkpoint database for the real failure reason. **Timeout errors are often misdiagnosed as rate limit failures.**

**Key indicator:** `"Node '<node_name>' timed out after <N>s"` in `channel_values.__error__`

**Root cause:** `NODE_TIMEOUTS` dict in `pipeline/retry.py` has a value too short for rate-limited API calls.

**Fix:** Increase the timeout for the affected node (e.g., `codegen: 180 → 300`).

**Reference:** See `references/checkpoint-timeout-debugging.md` for detailed investigation commands and general principle.

---

*Created from debugging session 2026-08-29: Fixed 4 failing tests in gd-gpt pipeline by applying these patterns.*