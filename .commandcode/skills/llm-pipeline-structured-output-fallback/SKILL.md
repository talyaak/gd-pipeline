---
name: llm-pipeline-structured-output-fallback
description: JSON prompting fallback for OpenAI-compatible APIs (OpenRouter, vLLM, LM Studio) where with_structured_output fails. Use when structured-output calls return 400/404/schema errors or when migrating a LangChain pipeline between LLM providers.
---

# LLM Pipeline: Structured Output Fallback for OpenAI-Compatible APIs

## Trigger
Use when migrating a LangChain pipeline from Anthropic (native `with_structured_output`) to OpenAI-compatible endpoints (OpenRouter, vLLM, LM Studio, etc.) that don't support the same structured output protocol.

## Problem
`llm.with_structured_output(Schema, method="function_calling")` works with Anthropic but fails on many OpenAI-compatible endpoints with errors like:
- `400: disable_parallel_tool_use not permitted`
- `404: Model not found` (when model name format differs)
- `Malformed input request: extraneous key [disable_parallel_tool_use]`

## Solution: JSON Prompting Pattern
Replace structured output calls with explicit JSON prompting + parsing:

```python
# BEFORE (Anthropic)
llm = get_review_llm().with_structured_output(GenreAnalysis, method="function_calling")
result: GenreAnalysis = llm.invoke(PROMPT.format(...))

# AFTER (OpenAI-compatible)
llm = get_review_llm()
raw = llm.invoke(PROMPT.format(...))
content = raw.content if hasattr(raw, "content") else str(raw)

# Extract JSON from response
try:
    start = content.find("{")
    end = content.rfind("}") + 1
    if start >= 0 and end > start:
        data = json.loads(content[start:end])
    else:
        raise ValueError("No JSON found")
except Exception:
    data = FALLBACK_DATA

result = Schema(**data)
```

## Prompt Requirements
Add explicit format instructions to the prompt:
```
Return a JSON object with these exact keys: field1, field2, field3. 
All values should be arrays of strings except field2 which should be a string.

Example format: {"field1": [...], "field2": "...", "field3": [...]}
```

## Normalization Layer
After parsing, normalize data to match schema expectations:
- Convert dict properties to list of keys
- Ensure numeric values are strings (if schema expects strings)
- Coerce arrays to proper types
- Provide sensible fallbacks for all required fields

## Nodes Updated (gd-gpt reference run)

Note for gd-pipeline: all nodes live in `pipeline/graph.py`; apply the same fallback pattern to every `with_structured_output` call site there.

Historical gd-gpt layout:
- `pipeline/nodes/research.py` — GenreAnalysis
- `pipeline/nodes/design.py` — GameDesignDocument  
- `pipeline/nodes/spec.py` — ImplementationSpec (with entity/balance normalization)
- `pipeline/nodes/review.py` — CodeReview

## Test Adaptation
Updated mock LLM classes in tests to return JSON strings instead of structured objects:
```python
def invoke(self, _prompt):
    if self._plain_values:
        return SimpleNamespace(content=self._plain_values.pop(0))
    if self._structured_value:
        return SimpleNamespace(content=json.dumps(self._structured_value.model_dump()))
```

## Pitfalls
- **Double-escaping**: JSON in prompts must use `{{` and `}}` for literal braces
- **Schema drift**: Pydantic models must match the JSON keys exactly
- **Missing fields**: Always provide fallback data for every required field
- **Type coercion**: Balance values as strings vs numbers — normalize explicitly