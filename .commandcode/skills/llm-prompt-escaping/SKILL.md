---
name: llm-prompt-escaping
description: Escape curly braces in LLM prompt templates to avoid Python format errors. Use when a prompt constant containing JSON examples throws KeyError or produces malformed prompts, or when writing prompt strings that will be .format()-ed.
---

When using LangChain (or similar LLMs) to format prompts that contain JSON examples or other curly-brace-delimited content, the curly braces may be interpreted as format placeholders, leading to KeyError or other formatting issues.

## Problem

Consider a prompt that includes a JSON object as an example:

    Return a JSON object with these keys:
    - color_palette: object mapping color names to hex strings (e.g., {"primary": "#ff0000", "background": "#000000"})

If this prompt is formatted using `.format()` or f-string-like mechanisms, the curly braces around the JSON object will be treated as placeholders, causing errors if the corresponding keys are not provided.

## Solution

Double the curly braces to escape them:

    Return a JSON object with these keys:
    - color_palette: object mapping color names to hex strings (e.g., {{"primary": "#ff0000", "background": "#000000"}})

This tells the formatter to treat the curly braces as literal characters.

## Examples in GD-GPT

1. Spec node fix: See `references/gd-gpt-spec-node-enforcement-example.md`.
2. Visual spec node fix: See `references/gd-gpt-visual-spec-enforcement-example.md`.
3. Recurring pattern meta-lesson: See `references/gd-gpt-recurring-pattern-lesson.md` — the same bug class appeared independently in two files; fix one, grep all.

## Prevention

Always double curly braces in JSON examples, code snippets, or any literal curly-brace content within LLM prompt templates that will be formatted.

**When fixing one instance, grep for others**: run `grep -n '{"' pipeline/nodes/*.py pipeline/nodes/*.txt` (or equivalent for your codebase) to catch un-escaped JSON examples across all prompt files before considering the fix complete.