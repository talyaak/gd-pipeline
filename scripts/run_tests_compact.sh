#!/bin/bash
# Headroom-style compression for our two noisiest, most repetitive sources:
# pytest output and pipeline verification runs. Full passing-test output adds
# nothing an agent needs to act on - only failures (with full traceback) and
# a summary line are worth putting in context. Full raw output is never
# discarded, just not sent to the model by default.
#
# Usage: scripts/run_tests_compact.sh [pytest args...]
# Full raw output is always saved to /tmp/last_test_run_full.log for anyone
# who needs to inspect a passing test's behavior, not just failures.

set -uo pipefail

# /workspace is a DrvFS/9p bind mount that repeatedly fails on uv's atomic
# install writes (hardlink-then-copy, temp-file-then-rename) with
# "Operation not permitted" - a real, recurring filesystem limitation, not a
# flaky fluke (hit it independently multiple times across days). Building
# the venv in /tmp (native container filesystem) instead avoids it entirely.
# Point PYTHONPATH at /workspace so the pipeline package itself still
# imports from the real source tree.
VENV="${TEST_VENV:-/tmp/venv_seed}"
if [ ! -x "$VENV/bin/python" ]; then
    uv venv "$VENV" --python 3.13 --clear >/dev/null 2>&1
    uv pip install --python "$VENV/bin/python" \
        pytest playwright langgraph langgraph-checkpoint-sqlite \
        langchain-anthropic langchain-openai langchain-core pydantic python-dotenv \
        >/dev/null 2>&1
fi

FULL_LOG="/tmp/last_test_run_full.log"
PYTHONPATH=/workspace "$VENV/bin/python" -m pytest "$@" > "$FULL_LOG" 2>&1
exit_code=$?

summary_line=$(grep -E '^=+ .*(passed|failed|error).* =+$' "$FULL_LOG" | tail -1)

if [ -z "$summary_line" ]; then
    echo "SUMMARY: pytest never produced a summary line - something failed before tests ran"
    echo "(uv/venv/import error, not a test failure). Showing the actual output, not omitting it:"
    echo ""
    cat "$FULL_LOG"
    exit "$exit_code"
fi

echo "SUMMARY: $summary_line"
echo ""

if [ "$exit_code" -eq 0 ]; then
    echo "All tests passed. Full output (with per-test detail) at $FULL_LOG if needed."
else
    echo "FAILURES (full tracebacks below; passing-test output omitted - see $FULL_LOG for that):"
    echo ""
    # pytest prints per-failure sections starting with "FAILED " in the short
    # summary, and full tracebacks under "=== FAILURES ===". Extract just that
    # section plus the short summary, skip the potentially-huge PASSED noise.
    awk '/^=+ FAILURES =+$/{flag=1} /^=+ short test summary/{flag=1} flag' "$FULL_LOG"
fi

exit "$exit_code"
