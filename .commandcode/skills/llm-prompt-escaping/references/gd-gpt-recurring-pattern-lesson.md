# Recurring Curly-Brace Escaping Pattern in GD-GPT

## Meta-Lesson

Two separate cycles (2026-08-30 ~01:05 and ~02:18, commits 3b87d40 and 424eb6b) each had to fix the same class of bug — literal `{`/`}` in a JSON example inside an LLM prompt string colliding with Python `.format()` / f-string placeholder syntax — once in `spec_prompt.txt` and again in `visual_spec.py`. Each fix was scoped to the one file that broke, without a sweep for the same pattern elsewhere.

## Root Cause

Prompt strings containing literal JSON examples are added ad hoc per node, with no shared templating helper, so the escaping rule has to be independently rediscovered each time a new prompt gets a JSON example.

## Prevention Going Forward

When fixing a curly-brace escaping issue in one prompt file, **always run a grep sweep** across all `pipeline/nodes/*prompt*` / prompt-containing files for un-escaped literal braces before assuming the current fix is the last one needed.

```bash
grep -n '{"' pipeline/nodes/*.py pipeline/nodes/*.txt
```

This catches JSON examples like `{"key": "value"}` that need to be `{{"key": "value"}}`.

## Reference

See `LESSONS_LEARNED.md` in the original gd-gpt repo (`C:\dev\gd-gpt`, committed at 88ece18) for the durable cross-cycle lesson.