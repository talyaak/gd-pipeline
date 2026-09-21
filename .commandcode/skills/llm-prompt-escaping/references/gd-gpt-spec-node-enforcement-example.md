# Fix for spec node curly brace escaping

In the gd-gpt project, the spec node's PROMPT string contained curly braces in a JSON example that were being interpreted as format placeholders by LangChain's string formatting, causing a KeyError.

The fix involved two steps:
1. Move the prompt to an external file (spec_prompt.txt) to avoid complex escaping in Python strings.
2. In the external file, double the curly braces to escape them:

Changed in spec_prompt.txt:
    "example": {"gravity": "1200", "jump_velocity": "-400"}

To:
    "example": {{\"gravity\": \"1200\", \"jump_velocity\": \"-400\"}}

(Note: In the external file, we need to double the braces because the file content is read as a string and then formatted. Actually, the fix was to double the braces in the Python string? Let's recall: the original fix was to escape the braces in the PROMPT string in spec.py by doubling them. Later, the prompt was moved to an external file to simplify.)

See the commit history for details.