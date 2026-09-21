# Debugging LangGraph Checkpoints for Node Timeout Failures

## Context

When a LangGraph pipeline running under Hermes cron fails with `failed_max_attempts` but no clear error in logs, the SQLite checkpoint database often contains the real failure reason.

## Pattern: Node Timeout Diagnosis

**Symptom:** Pipeline checkpoint shows `status: "failed_max_attempts"` for codegen/execution nodes, but no LLM error in output.

**Investigation:**

```bash
# 1. Find latest run directory
ls -t output/ | head -1

# 2. Inspect checkpoint.sqlite
sqlite3 output/<run_dir>/checkpoint.sqlite "
SELECT thread_id, checkpoint->>'channel_values' as state
FROM checkpoints
ORDER BY thread_id DESC LIMIT 1;
"
```

**Key evidence to look for in checkpoint state:**
- `channel_values` → `__error__` field contains actual exception
- Look for `"Node '<node_name>' timed out after <N>s"` — this is a **timeout**, not a rate limit
- The timeout value comes from `NODE_TIMEOUTS` dict in `pipeline/retry.py`

## Root Cause Example (this session)

```
Node 'codegen' timed out after 180s
```

**Cause:** `NODE_TIMEOUTS["codegen"] = 180` was too short for rate-limited API calls. A single LLM call during rate limit window exceeded 180s.

**Fix:** Increase timeout in `pipeline/retry.py`:
```python
NODE_TIMEOUTS = {
    "codegen": 300,  # was 180
    ...
}
```

## General Principle

**Timeout errors in checkpoints are often misdiagnosed as rate limit failures.** The retry logic (backoff, max attempts) handles rate limits correctly — the timeout is a separate guard that kills the node attempt prematurely.

When both rate limits AND timeouts exist:
- Rate limit → retry with backoff (handled by `invoke_with_retry`)
- Timeout → node attempt killed, counts as failed attempt (handled by LangGraph's timeout)

**Fix order:**
1. Increase timeout to accommodate worst-case rate limit delay
2. Verify retries work within the new timeout window
3. Only then adjust retry parameters if needed

## Quick Commands

```bash
# Check all recent runs for timeout errors
for dir in output/*/; do
  sqlite3 "$dir/checkpoint.sqlite" "
    SELECT json_extract(checkpoint, '$.channel_values.__error__') as error
    FROM checkpoints
    WHERE json_extract(checkpoint, '$.channel_values.__error__') LIKE '%timed out%';
  " 2>/dev/null && echo "=== $dir ===";
done

# Run gate check to see pipeline status (gd-pipeline: use `python -m pipeline`)
PYTHONPATH=. python3 -m pipeline
```