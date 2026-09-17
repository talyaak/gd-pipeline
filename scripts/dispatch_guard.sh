#!/usr/bin/env bash
# Anti-fabrication guard wrapper for Hermes dispatches.
#
# Mechanizes the manual pre/post snapshot + prefix-hash-match check that
# caught all three destructive test-file failures this round (identity
# hallucination, and two separate write_file wholesale-overwrite
# incidents), moving it outside the model's own control: this script
# snapshots the target file(s) BEFORE dispatch, runs the dispatch, then
# independently verifies append-only invariants AFTER -- auto-discarding
# via `git checkout --` on any violation, before any human/Claude review
# even looks at the result.
#
# FAIL-CLOSED BY DESIGN: a guard that can silently report PASS when the
# dispatch itself never ran, crashed, or partially wrote is worse than no
# guard (gate finding on an earlier version of this script -- it printed
# PASS on an unchanged target when the outer WSL/docker-exec call itself
# was stubbed to fail, because only the append-only invariant was ever
# checked, never the dispatch's own execution status). This version:
#   - captures and validates the outer WSL/docker-exec exit status AND
#     Hermes's own exit status (read back from an explicit marker line in
#     the dispatch log) -- either being nonzero, or the marker being
#     absent/malformed, is treated as a dispatch failure regardless of
#     what the target files look like afterward.
#   - on ANY dispatch-level failure, still runs the full verify+discard
#     pass on every target (a crash mid-write must not survive just
#     because we're already failing for a different reason), then exits
#     nonzero.
#   - never prints "Discarded" unless the discard actually succeeded --
#     checkout's own exit status is checked, and if it fails, the wrapper
#     says explicitly that targets may still be modified.
#   - preflights that every target is a tracked, restorable file (git
#     ls-files --error-unmatch) BEFORE dispatching anything, so an
#     unrestorable target is caught up front, not discovered mid-failure.
#   - uses a cleanup trap so an interrupted run can't leave a stray
#     .guard_*_prompt.md file behind.
#   - compares BYTE counts and byte-prefixes, not line counts / `head -n`
#     -- a trailing-newline-only change can make `wc -l` under-count in a
#     way that lets a real change slip past a line-based check; byte
#     comparison has no such edge case.
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
#         for EVERY target file, that after a SUCCESSFUL dispatch:
#           (a) byte count did not decrease
#           (b) the first N bytes (N = pre-dispatch byte count) are
#               byte-for-byte identical to the entire pre-dispatch file
#         i.e. the file must be provably unchanged for all of its
#         original content, with only new bytes appended at the end.
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
# Exit codes:
#   0  PASS -- dispatch succeeded (verified exit status) and the
#      append-only invariant held for every target. Files are left as
#      the dispatch produced them, for further review/testing.
#   1  FAIL, discarded -- either the dispatch itself failed/could not be
#      verified, or an invariant was violated. All targets were
#      successfully restored to their pre-dispatch state.
#   3  FAIL, discard incomplete -- a failure was detected but restoring
#      one or more targets via `git checkout --` did NOT succeed. Targets
#      may still be in a modified/inconsistent state. Caller MUST check
#      `git status` on the listed targets before trusting anything.
#   2  setup error (bad usage, missing files, untracked target) -- no
#      dispatch was attempted.

set -uo pipefail
# Deliberately not using `set -e`: this script's correctness depends on
# explicitly capturing and checking the exit status of every operation
# that matters (the outer dispatch call, the hermes exit marker, the
# discard checkout) rather than relying on -e, whose behavior inside
# conditionals/pipelines/command-substitutions is notoriously easy to get
# wrong in exactly the "silently didn't stop when it should have" way
# this rewrite exists to eliminate. Every exit status this script cares
# about is captured into a variable and checked explicitly below.

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
  echo "SETUP FAIL: unsupported mode '$MODE' (only 'append-only' is implemented)" >&2
  exit 2
fi

if [ ! -d "$HOST_WORKTREE" ]; then
  echo "SETUP FAIL: host worktree path not found: $HOST_WORKTREE" >&2
  exit 2
fi

if [ ! -f "$PREAMBLE_FILE" ]; then
  echo "SETUP FAIL: preamble file not found at $PREAMBLE_FILE" >&2
  exit 2
fi

if [ ! -f "$PROMPT_FILE" ]; then
  echo "SETUP FAIL: prompt file not found at $PROMPT_FILE" >&2
  exit 2
fi

# --- Preflight: every target must exist AND be a tracked, restorable file. ---
( cd "$HOST_WORKTREE" || exit 2
  for t in "${TARGETS[@]}"; do
    if [ ! -f "$t" ]; then
      echo "SETUP FAIL: target file does not exist: $t" >&2
      exit 2
    fi
    if ! git ls-files --error-unmatch -- "$t" >/dev/null 2>&1; then
      echo "SETUP FAIL: target file is not tracked by git (not restorable via checkout): $t" >&2
      exit 2
    fi
  done
) || exit 2

RUN_ID="guard_$(date +%s)_$$"
COMBINED_PROMPT="$HOST_WORKTREE/.guard_${RUN_ID}_prompt.md"
PROMPT_BASENAME=".guard_${RUN_ID}_prompt.md"
LOG_FILE="/tmp/${RUN_ID}_log.txt"

# Cleanup trap: the temp prompt file living inside the worktree must never
# survive this script, regardless of how it exits (normal exit, error
# return, or external interruption).
cleanup() { rm -f "$COMBINED_PROMPT" 2>/dev/null; }
trap cleanup EXIT INT TERM

cat "$PREAMBLE_FILE" "$PROMPT_FILE" > "$COMBINED_PROMPT"

echo "== dispatch_guard: run $RUN_ID, mode=$MODE =="
echo "== host worktree: $HOST_WORKTREE =="
echo "== container worktree: $CONTAINER_WORKTREE =="
echo "== targets: ${TARGETS[*]} =="

# --- Step 1: snapshot every target file BEFORE dispatch (host-side, byte-based). ---
declare -A PRE_BYTES
declare -A PRE_HASH
for t in "${TARGETS[@]}"; do
  f="$HOST_WORKTREE/$t"
  bytes=$(wc -c < "$f" | tr -d '[:space:]')
  hash=$(sha256sum "$f" | cut -d' ' -f1)
  PRE_BYTES["$t"]="$bytes"
  PRE_HASH["$t"]="$hash"
  echo "  pre  $t: bytes=$bytes hash=$hash"
done

# --- Step 2: run the dispatch, capturing BOTH the outer call's own exit
#     status and Hermes's own exit status (read back from an explicit
#     marker line this script requires be present in the log). ---
wsl.exe -e bash -lc "docker exec hermes-gateway bash -c 'cd \"$CONTAINER_WORKTREE\" && hermes chat -q \"\$(cat \"$PROMPT_BASENAME\")\" --yolo > \"$LOG_FILE\" 2>&1; echo DISPATCH_EXIT=\$? >> \"$LOG_FILE\"'"
OUTER_STATUS=$?
echo "== dispatch invocation finished, outer status=$OUTER_STATUS (log: $LOG_FILE inside container) =="

DISPATCH_OK=1
if [ "$OUTER_STATUS" -ne 0 ]; then
  echo "  DISPATCH FAILURE: outer WSL/docker-exec call returned nonzero ($OUTER_STATUS)"
  DISPATCH_OK=0
fi

# Read the log back from inside the container to check Hermes's own exit
# marker. Absent or malformed = treated as failure, same as nonzero.
LOG_CONTENT=$(wsl.exe -e bash -lc "docker exec hermes-gateway bash -c 'tail -c 4096 \"$LOG_FILE\" 2>/dev/null'" 2>/dev/null)
HERMES_EXIT_LINE=$(echo "$LOG_CONTENT" | grep -o 'DISPATCH_EXIT=[0-9-]*' | tail -1)
if [ -z "$HERMES_EXIT_LINE" ]; then
  echo "  DISPATCH FAILURE: no DISPATCH_EXIT marker found in the dispatch log -- cannot confirm Hermes actually completed"
  DISPATCH_OK=0
else
  HERMES_EXIT="${HERMES_EXIT_LINE#DISPATCH_EXIT=}"
  if ! [[ "$HERMES_EXIT" =~ ^[0-9]+$ ]]; then
    echo "  DISPATCH FAILURE: malformed DISPATCH_EXIT marker ('$HERMES_EXIT_LINE')"
    DISPATCH_OK=0
  elif [ "$HERMES_EXIT" -ne 0 ]; then
    echo "  DISPATCH FAILURE: Hermes itself exited nonzero ($HERMES_EXIT)"
    DISPATCH_OK=0
  else
    echo "  dispatch exit marker OK (DISPATCH_EXIT=0)"
  fi
fi

# --- Step 3: verify invariants AFTER dispatch (host-side, byte-based).
#     Runs regardless of DISPATCH_OK -- a failed/crashed/partial dispatch
#     can still have written something, and every target must be checked
#     and, if changed at all, discarded, before this script exits. ---
VIOLATION=0
for t in "${TARGETS[@]}"; do
  f="$HOST_WORKTREE/$t"
  if [ ! -f "$f" ]; then
    echo "  VIOLATION: $t -- file missing after dispatch"
    VIOLATION=1
    continue
  fi
  post_bytes=$(wc -c < "$f" | tr -d '[:space:]')
  pre_bytes="${PRE_BYTES[$t]}"
  pre_hash="${PRE_HASH[$t]}"
  if [ "$post_bytes" -lt "$pre_bytes" ]; then
    echo "  VIOLATION: $t -- byte count decreased ($pre_bytes -> $post_bytes)"
    VIOLATION=1
    continue
  fi
  prefix_hash=$(head -c "$pre_bytes" "$f" | sha256sum | cut -d' ' -f1)
  if [ "$prefix_hash" != "$pre_hash" ]; then
    echo "  VIOLATION: $t -- first $pre_bytes bytes no longer match the pre-dispatch file (prefix_hash=$prefix_hash, expected=$pre_hash)"
    VIOLATION=1
    continue
  fi
  echo "  post $t: bytes=$post_bytes OK (append-only invariant held)"
done

# --- Step 4: decide PASS/FAIL. A dispatch failure fails the run even if
#     every target happens to look byte-identical (the silent-PASS case
#     the gate review caught) -- and either way, if anything was flagged
#     as changed (VIOLATION), or the dispatch itself failed, discard. ---
if [ "$DISPATCH_OK" -eq 0 ] || [ "$VIOLATION" -eq 1 ]; then
  if [ "$DISPATCH_OK" -eq 0 ]; then
    echo "== FAIL: dispatch execution could not be verified as successful =="
  fi
  if [ "$VIOLATION" -eq 1 ]; then
    echo "== FAIL: append-only invariant violated =="
  fi
  echo "== discarding all targets (host-side git checkout) =="
  CHECKOUT_ERR=$( cd "$HOST_WORKTREE" && git checkout -- "${TARGETS[@]}" 2>&1 )
  CHECKOUT_STATUS=$?
  if [ "$CHECKOUT_STATUS" -eq 0 ]; then
    # Verify the checkout actually restored pre-dispatch content, not
    # just that the command returned 0 -- belt and suspenders.
    RESTORE_OK=1
    for t in "${TARGETS[@]}"; do
      f="$HOST_WORKTREE/$t"
      cur_hash=$(sha256sum "$f" | cut -d' ' -f1)
      if [ "$cur_hash" != "${PRE_HASH[$t]}" ]; then
        RESTORE_OK=0
        echo "  RESTORE FAILED (post-checkout hash mismatch): $t"
      fi
    done
    if [ "$RESTORE_OK" -eq 1 ]; then
      echo "== Discarded. All targets confirmed restored to their pre-dispatch state. =="
      exit 1
    else
      echo "== git checkout returned success but at least one target's content does NOT match its pre-dispatch hash. Targets may still be modified. Run 'git status' on them before trusting anything. ==" >&2
      exit 3
    fi
  else
    echo "== git checkout -- FAILED (exit $CHECKOUT_STATUS): $CHECKOUT_ERR ==" >&2
    echo "== Targets may still be modified. Do NOT assume they were discarded. Run 'git status' on them before trusting anything. ==" >&2
    exit 3
  fi
fi

echo "== PASS: dispatch verified successful and append-only invariant held for all targets =="
exit 0
