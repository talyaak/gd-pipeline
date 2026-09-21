# Fix for visual_spec.py curly brace escaping

In the gd-gpt project, the visual_spec.py node's PROMPT string contained a JSON example with curly braces that were being interpreted as format placeholders by LangChain's string formatting, causing a KeyError.

The fix was to double the curly braces in the JSON example:

Changed:
    - color_palette: object mapping color names to hex strings (e.g., {\"primary\": \"#ff0000\", \"background\": \"#000000\"})

To:
    - color_palette: object mapping color names to hex strings (e.g., {{\"primary\": \"#ff0000\", \"background\": \"#000000\"}})

This ensures the curly braces are treated as literal characters in the prompt.

See also: references/gd-gpt-spec-node-enforcement-example.md for the spec node fix.