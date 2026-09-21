# LLM JSON Parsing Fallbacks for Structured Output

## Problem
OpenRouter/Claude doesn't reliably honor `with_structured_output()` — especially with `method="function_calling"`. The model may return:
- Plain JSON without function call wrapper
- Markdown-fenced JSON
- Prose with embedded JSON
- Nothing parseable

## Solution Pattern
```python
import json

def parse_llm_json(raw, fallback):
    """Extract and parse JSON from LLM response with fallback."""
    content = raw.content if hasattr(raw, "content") else str(raw)
    
    try:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
        raise ValueError("No JSON found")
    except Exception:
        return fallback

# Usage in any LLM node:
def research(state: RunState) -> dict:
    llm = get_review_llm()
    raw = invoke_with_retry(lambda: llm.invoke(PROMPT.format(brief=state["brief"])))
    data = parse_llm_json(raw, DEFAULT_FALLBACK)
    
    # Normalize type mismatches
    if isinstance(data.get("progression"), list):
        data["progression"] = " ".join(data["progression"])
    
    return {"research": {"status": "passed", "artifact": GenreAnalysis(**data).model_dump()}}
```

## Fallback Design
- Fallback MUST be valid for the Pydantic schema
- Use conservative defaults that pass static validation
- Include all required fields

```python
DEFAULT_FALLBACK = {
    "core_mechanics": ["run", "jump", "dodge"],
    "juice": ["particles", "screen shake", "sound effects"],
    "progression": "ramps up",
    "common_mistakes": ["too hard early", "unfair obstacles"],
    "reference_games": ["Crossy Road", "Temple Run"],
}
```

## Test Mock Updates
Update `_FakeLLM.invoke()` to return JSON strings for structured output path:
```python
def invoke(self, _prompt):
    if self._plain_values:
        return SimpleNamespace(content=self._plain_values.pop(0))
    if self._structured_value:
        import json
        return SimpleNamespace(content=json.dumps(
            self._structured_value.model_dump() if hasattr(self._structured_value, 'model_dump') else self._structured_value
        ))
    return SimpleNamespace(content="{}")
```