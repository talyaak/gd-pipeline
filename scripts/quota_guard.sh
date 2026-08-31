#!/bin/bash
# Mechanically pauses the gd-gpt-autonomous-dev cron job once it's racked up
# enough OpenRouter free-tier daily rate-limit hits that further attempts are
# pure waste (each failed cycle still burns retries/log noise/container CPU
# for nothing), and resumes it once the daily quota window has reset.
#
# This is deliberately NOT something we ask the agent to self-police in its
# own prompt — an LLM deciding "should I stop trying" from inside a cycle
# that's already failing is exactly the kind of self-assessment this project
# stopped trusting for other checks (see gate_check.py). This script is pure
# shell/state inspection, run on a schedule, independent of the agent.
set -euo pipefail

JOB_ID="220e71a987bf"
THRESHOLD=15
LOG_FILE="$HOME/.hermes/logs/agent.log"
GUARD_LOG="$HOME/.hermes/quota_guard.log"

TODAY="$(date -u +%Y-%m-%d)"
HOUR="$(date -u +%H)"
TS="$(date -u +"%Y-%m-%d %H:%M:%S")"

COUNT=0
if [ -f "$LOG_FILE" ]; then
    COUNT="$(awk -v d="$TODAY" 'index($0, d) == 1' "$LOG_FILE" | grep -c 'Rate limit exceeded' || true)"
fi

LIST_OUTPUT="$(hermes cron list --all 2>&1)"

IS_ACTIVE="no"
if echo "$LIST_OUTPUT" | grep -q "${JOB_ID} \[active\]"; then
    IS_ACTIVE="yes"
fi

IS_PAUSED="no"
if echo "$LIST_OUTPUT" | grep -q "${JOB_ID} \[paused\]"; then
    IS_PAUSED="yes"
fi

if [ "$IS_ACTIVE" = "yes" ] && [ "$COUNT" -ge "$THRESHOLD" ]; then
    hermes cron pause "$JOB_ID" >/dev/null 2>&1
    echo "$TS | PAUSED $JOB_ID - $COUNT rate-limit hits today (threshold $THRESHOLD)" >> "$GUARD_LOG"
elif [ "$IS_PAUSED" = "yes" ] && [ "$HOUR" = "00" ]; then
    hermes cron resume "$JOB_ID" >/dev/null 2>&1
    echo "$TS | RESUMED $JOB_ID at UTC midnight reset" >> "$GUARD_LOG"
else
    echo "$TS | checked: active=$IS_ACTIVE paused=$IS_PAUSED count=$COUNT (no action)" >> "$GUARD_LOG"
fi
