#!/usr/bin/env bash
# Anti-fabrication guard wrapper for Hermes dispatches.
#
# Mechanizes the manual pre/post snapshot + head-hash-match check that
# caught all three destructive test-file failures this round (identity
# hallucination, and two separate write_file wholesale-overwrite
# incidents), moving it outside the model's own control: this script
# snapshots the target file(s) BEFORE dispatch, runs the dispatch, then
# independently verifies append-only invariants AFTER -- auto-discarding
# via `git checkout --` on any violation, before any human/Claude review
# even looks at the result.
#
# IMPORTANT: all snapshot/verify/discard file operations run on the HOST
# (this script itself, in git-bash), directly against the worktree's
# actual filesystem path -- NOT via `docker exec`. git is broken inside
# the hermes-gateway container for these worktrees (a known quirk: the
# worktree's .git pointer files store host paths meaningless in Linux),
# so `git checkout --` must run where git actually works. The host and
# container share the same bind-mounted files, so a host-side discard
# correctly undoes whatever the container-side dispatch wrote. The
# container is used ONLY to invoke `hermes chat` itself.
#
# Usage:
#   dispatch_guard.sh <mode> <host_worktree_path> <container_worktree_path> <prompt_file> <target_file> [<target_file2> ...]
#
#   mode: "append-only" -- the only mode implemented so far. Requires,
#         for EVERY target file, that after the dispatch:
#           (a) line count did not decrease
#           (b) the first N lines (N = pre-dispatch line count) hash
#               EXACTLY match the pre-dispatch file's own full hash
#         i.e. the file must be provably unchanged for all of its
#         original content, with only new lines appended at the end.
#         Any violation on ANY target file discards ALL target files
#         (git checkout --, run on the host) and the wrapper reports FAIL.
#
#   host_worktree_path: git-bash-style path on THIS machine, e.g.
#         /c/Dev/gd-gpt/.claude/worktrees/farm-idle-collectible-world
#
#   container_worktree_path: absolute path inside the hermes-gateway
#         container, e.g.
#         /workspace/.claude/worktrees/farm-idle-collectible-world
#         (used only as the cwd for the hermes dispatch)
#
#   prompt_file: path (host, git-bash-style) to the task-specific prompt.
#         This script prepends the standing preamble
#         (hermes_dispatch_preamble.md, expected alongside this script)
#         automatically -- the caller does not need to include it.
#
#   target_file: path RELATIVE to the worktree root, e.g.
#         tests/test_farm_idle_real_device.py. Repeatable.
#
# Exit code: 0 on PASS (dispatch ran, all invariants held -- files are
#            left as the dispatch produced them, for further review/
#            testing by the caller). Non-zero on FAIL (files were
#            auto-discarded back to their pre-dispatch state on the host)
#            or on a setup/dispatch-execution error.
#
# The dispatch itself runs attached, synchronously (never
# `docker exec -d`), per this pipeline's standing rule against detached
# dispatches (an earlier false-exit-signal incident banned that pattern).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREAMBLE_FILE="$SCRIPT_DIR/hermes_dispatch_preamble.md"

if [ "$#" -lt 5 ]; then
  echo "Usage: $0 <mode> <host_worktree_path> <container_worktree_path> <prompt_file> <target_file> [<target_file2> ...]" >&2
  exit 2
fi

MODE="$1"
HOST_WORKTREE="$2"
CONTAINER_WORKTREE="$3"
PROMPT_FILE="$4"
shift 4
TARGETS=("$@")

if [ "$MODE" != "append-only" ]; then
  echo "FAIL: unsupported mode '$MODE' (only 'append-only' is implemented)" >&2
  exit 2
fi

if [ ! -d "$HOST_WORKTREE" ]; then
  echo "FAIL: host worktree path not found: $HOST_WORKTREE" >&2
  exit 2
fi

if [ ! -f "$PREAMBLE_FILE" ]; then
  echo "FAIL: preamble file not found at $PREAMBLE_FILE" >&2
  exit 2
fi

if [ ! -f "$PROMPT_FILE" ]; then
  echo "FAIL: prompt file not found at $PROMPT_FILE" >&2
  exit 2
fi

RUN_ID="guard_$(date +%s)_$$"
COMBINED_PROMPT="$HOST_WORKTREE/.guard_${RUN_ID}_prompt.md"
cat "$PREAMBLE_FILE" "$PROMPT_FILE" > "$COMBINED_PROMPT"

echo "== dispatch_guard: run $RUN_ID, mode=$MODE =="
echo "== host worktree: $HOST_WORKTREE =="
echo "== container worktree: $CONTAINER_WORKTREE =="
echo "== targets: ${TARGETS[*]} =="

# --- Step 1: snapshot every target file BEFORE dispatch (host-side) ---
declare -A PRE_LINES
declare -A PRE_HASH
for t in "${TARGETS[@]}"; do
  f="$HOST_WORKTREE/$t"
  if [ ! -f "$f" ]; then
    echo "FAIL: target file not found before dispatch: $f" >&2
    rm -f "$COMBINED_PROMPT"
    exit 2
  fi
  lines=$(wc -l < "$f" | tr -d '[:space:]')
  hash=$(sha256sum "$f" | cut -d' ' -f1)
  PRE_LINES["$t"]="$lines"
  PRE_HASH["$t"]="$hash"
  echo "  pre  $t: lines=$lines hash=$hash"
done

# --- Step 2: copy combined prompt into the container, run dispatch attached ---
# (the prompt file lives inside the worktree itself, which is bind-mounted
# into the container at CONTAINER_WORKTREE, so no separate docker cp needed
# for the prompt -- just reference it by its container-side path.)
PROMPT_BASENAME="$(basename "$COMBINED_PROMPT")"
LOG_FILE="/tmp/${RUN_ID}_log.txt"
wsl.exe -e bash -lc "docker exec hermes-gateway bash -c 'cd \"$CONTAINER_WORKTREE\" && hermes chat -q \"\$(cat \"$PROMPT_BASENAME\")\" --yolo > \"$LOG_FILE\" 2>&1; echo DISPATCH_EXIT=\$? >> \"$LOG_FILE\"'"
echo "== dispatch finished (log: $LOG_FILE inside container) =="

rm -f "$COMBINED_PROMPT"

# --- Step 3: independently verify invariants AFTER dispatch (host-side) ---
VIOLATION=0
for t in "${TARGETS[@]}"; do
  f="$HOST_WORKTREE/$t"
  if [ ! -f "$f" ]; then
    echo "  VIOLATION: $t -- file missing after dispatch"
    VIOLATION=1
    continue
  fi
  post_lines=$(wc -l < "$f" | tr -d '[:space:]')
  pre_lines="${PRE_LINES[$t]}"
  pre_hash="${PRE_HASH[$t]}"
  if [ "$post_lines" -lt "$pre_lines" ]; then
    echo "  VIOLATION: $t -- line count decreased ($pre_lines -> $post_lines)"
    VIOLATION=1
    continue
  fi
  head_hash=$(head -n "$pre_lines" "$f" | sha256sum | cut -d' ' -f1)
  if [ "$head_hash" != "$pre_hash" ]; then
    echo "  VIOLATION: $t -- first $pre_lines lines no longer hash-match the pre-dispatch file (head_hash=$head_hash, expected=$pre_hash)"
    VIOLATION=1
    continue
  fi
  echo "  post $t: lines=$post_lines OK (append-only invariant held)"
done

if [ "$VIOLATION" -eq 1 ]; then
  echo "== FAIL: invariant violated -- auto-discarding all target files (host-side git checkout) =="
  ( cd "$HOST_WORKTREE" && git checkout -- "${TARGETS[@]}" )
  echo "== Discarded. Verify with git status if needed. =="
  exit 1
fi

echo "== PASS: append-only invariant held for all targets =="
exit 0
