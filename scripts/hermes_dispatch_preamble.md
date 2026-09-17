## Standing rules for this dispatch (non-optional, apply regardless of task content below)

1. **git is broken in this container for this worktree** (a known, harmless infrastructure quirk -- the worktree's `.git` pointer file stores a Windows host path meaningless inside this Linux container). Every git command will fail with `fatal: not a git repository`. Do NOT run any git command. Do NOT try to diagnose or fix it. Do NOT interpret a git error as a sign you're in the wrong worktree, that a file is stale, or that "the real" file might exist elsewhere. It never does. File identity is established ONLY by the exact facts stated in the task below (line count, sha256 -- both obtained via plain filesystem commands, neither depends on git).

2. **Never reconstruct destroyed or missing content from memory.** If a file you are editing appears shorter, different, or missing content you expect, STOP immediately and report exactly what you observed (actual line count, actual content around the discrepancy). Do not attempt to "restore" or "rewrite" what you believe was there. Do not guess. A wrong guess written back to the file is worse than stopping.

3. **Never search other worktrees, branches, or directories for "the real" or "original" version of a file.** The file at the exact path given in this task's identity block, in the current working directory, is the only correct file. If its measured identity (line count / hash) doesn't match what the task states, stop and report the mismatch -- do not go looking elsewhere for an explanation.

4. **Prefer targeted edits (patch/diff-style) over whole-file rewrites** (e.g. `write_file` replacing entire file contents) wherever the task allows it. A rewrite that goes wrong destroys everything; a failed targeted edit typically fails visibly and leaves the rest of the file intact.

5. **After any edit, verify with plain filesystem tools before claiming success**: `wc -l`, `sha256sum`, and (for JS/Python) a syntax check (`node -c` / `python -c "import ast; ast.parse(...)"`). Your own claim of success is not sufficient and will be independently re-verified regardless -- these checks are for your own benefit, to catch a problem before you report one.

---

