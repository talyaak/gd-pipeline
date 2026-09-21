# Rate-Limit-Aware Retry Patterns for LLM APIs

## Problem

Free-tier LLM APIs (OpenRouter, Anthropic, etc.) enforce minute-level rate limits (~20 req/min). Standard exponential backoff (2s → 4s → 8s = 14s total) is **insufficient** — the rate limit window hasn't reset, causing cascading 429 errors and truncated responses that fail downstream validation.

## Root Cause Pattern

| Factor | Typical Value |
|--------|--------------|
| Free-tier rate limit | 20 requests/minute |
| LLM calls per pipeline run | 15+ |
| Cron frequency | ~2 minutes |
| Standard backoff (2s base) | 2s + 4s + 8s = 14s max wait |
| Rate limit reset window | ~60 seconds |

**Result:** Retries happen within the same rate-limit window → guaranteed 429 → truncated output → validation failure.

## Solution: Category-Aware Backoff

Classify errors and apply different backoff strategies:

```python
# TRANSIENT (network, rate limit) → 30s base: 30s, 60s, 120s (total ~210s)
# SYNTAX, VALIDATION, etc. → configured base (2s): 2s, 4s, 8s
```

**Implementation** (from `pipeline/retry.py`):
```python
def _calculate_delay(attempt: int, error_category: ErrorCategory) -> float:
    base = RETRY_BASE_DELAY_SECONDS  # 2s default
    if error_category == ErrorCategory.TRANSIENT:
        # Rate limits need minute-level waits
        base = 30.0
    return base * (2 ** attempt)
```

## Debugging Checklist for Rate-Limit Issues

When LLM outputs are truncated/incomplete and validation fails:

1. **Check error category** — Is the LLM client raising `RateLimitError` (→ TRANSIENT)?
2. **Measure call volume** — How many LLM calls per run? × cron frequency?
3. **Verify backoff math** — Total wait time > rate limit reset window?
4. **Add instrumentation** — Log rate limit headers, retry counts, wait times
5. **Test with longer backoff** — 30s base for TRANSIENT errors

## Applicable When

- Using free-tier LLM APIs with known rate limits
- Running automated pipelines at frequency > rate limit window
- Seeing "incomplete HTML" / "missing Phaser.Game" validation errors that correlate with 429 responses
- Retry logic exists but uses uniform backoff for all error types

## Key Insight

**Error categorization enables targeted backoff.** Not all errors need long waits — syntax errors need fast retries. Only TRANSIENT (network/rate-limit) errors benefit from minute-level backoff. This keeps the pipeline responsive for real bugs while surviving rate limits.