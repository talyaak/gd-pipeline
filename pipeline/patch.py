"""Exact-string-replacement patching, shared by codegen's surgical-rework loop.

Deliberately mirrors the semantics of a coding-agent's own edit tool: each edit
must match its old_string exactly once in the current text (context included
by the caller if needed for uniqueness). Edits are applied in order against the
progressively-patched text, so edit N sees the result of edits 1..N-1 — this
lets a model reference code it just introduced.
"""


def apply_edits(text: str, edits: list[dict]) -> tuple[str, list[str]]:
    """Apply a sequence of {"old_string": ..., "new_string": ...} edits.

    Returns (patched_text, errors). An edit is skipped (not applied) and
    recorded as an error if its old_string is absent or ambiguous (appears
    more than once) in the text at the time it's evaluated — never guess.
    """
    errors: list[str] = []
    for i, edit in enumerate(edits):
        old = edit.get("old_string")
        new = edit.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str) or old == "":
            errors.append(f"edit {i}: malformed (old_string/new_string missing or old_string empty)")
            continue
        count = text.count(old)
        if count == 0:
            snippet = old if len(old) <= 120 else old[:120] + "..."
            errors.append(f"edit {i}: old_string not found (no exact match): {snippet!r}")
            continue
        if count > 1:
            snippet = old if len(old) <= 120 else old[:120] + "..."
            errors.append(f"edit {i}: old_string not unique (found {count} times) — include more surrounding context: {snippet!r}")
            continue
        text = text.replace(old, new, 1)
    return text, errors
