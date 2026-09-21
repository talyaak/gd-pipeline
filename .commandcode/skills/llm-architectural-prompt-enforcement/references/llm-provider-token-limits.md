# LLM Provider Token Limits and Silent Fallback Detection

## Problem

LLM providers (OpenRouter, Anthropic, etc.) enforce output token limits per model. When a request's `max_tokens` exceeds the model's maximum, the provider may **silently fall back to a different model** (often a free/low-quality tier) without raising an error. This produces degraded output that fails downstream validation but leaves no obvious trace in logs.

## Root Cause Pattern

| Factor | Typical Value |
|--------|--------------|
| claude-sonnet-4 max output | 8,192 tokens |
| Configured CODEGEN_MAX_TOKENS | 48,000 tokens |
| Provider behavior on overflow | Silent fallback to free model |
| Free model quality | Significantly lower (e.g., cohere/north-mini-code:free) |
| Cost tracker anomaly detection | Detects free model usage despite paid model config |

## Detection via Cost Tracking

The pipeline's `pipeline/cost_tracker.py` logs every LLM call with model name and estimated cost. When a paid model is configured but free models appear in logs:

```json
{
  "node": "codegen",
  "model": "cohere/north-mini-code:free",  // Should be "anthropic/claude-sonnet-4"
  "input_tokens": 5219,
  "output_tokens": 48000,  // Hits the configured limit, not model's real limit
  "cost_usd": null
}
```

**Key signal:** `cost_usd: null` for a model not in the pricing table, combined with output_tokens matching the configured limit (not the model's real limit).

## Solution: Match Configuration to Model Reality

```python
# In config.py - use the model's ACTUAL max output tokens
CODEGEN_MAX_TOKENS = int(os.environ.get("CODEGEN_MAX_TOKENS", "8192"))  # claude-sonnet-4 limit
```

## Prevention Checklist

When configuring LLM generation limits:

1. **Verify model's actual max output tokens** from provider documentation
2. **Set `max_tokens` ≤ model limit** (with small buffer)
3. **Monitor cost tracker logs** for unexpected model names or `cost_usd: null`
4. **Add automated check** in CI: validate configured limits against known model limits
5. **Test with known-complex prompts** to verify no silent fallback occurs

## Debugging Checklist for Silent Fallback

When generation quality degrades unexpectedly:

1. **Check cost tracker** — Does `model` match configured model? Is `cost_usd` null?
2. **Compare output_tokens** — Does it hit the configured limit exactly (suggests truncation at fallback model's limit)?
3. **Verify provider docs** — What is the model's actual max output?
4. **Check provider dashboard** — Some show fallback events
5. **Reduce max_tokens** — If it fixes quality, fallback was occurring

## Applicable When

- Using provider APIs with per-model token limits (OpenRouter, Anthropic, OpenAI)
- Configuring high `max_tokens` for complex generation tasks
- Seeing quality degradation that correlates with output length
- Cost tracking shows unexpected model names or null costs
- Validation fails with "incomplete/truncated" patterns despite no error from LLM client

## Key Insight

**Token limit configuration is a trust boundary.** The LLM client library won't validate your `max_tokens` against the model's real limit — it passes it through. The provider then decides what to do (error, truncate, or fallback). Always configure limits based on the *specific model's documented maximum*, not on desired output length.