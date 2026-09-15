#!/usr/bin/env bash
# Instinct Wire watcher: polls the "Instinct Wire" GitHub issue on
# talyaak/gd-pipeline for new comments, and appends every comment that is
# BOTH marked **[INSTINCT]** AND authored by the account named in
# INSTINCT_GH_USER (config) to a local inbox log. Nothing here injects
# content into any live process automatically -- delivery is a plain file
# the Claude session reads on its own schedule, as data to evaluate, same
# trust model as the existing email channel.
#
# Security invariant (do not weaken this): the marker alone is NEVER
# sufficient. A comment must be authored by INSTINCT_GH_USER (a GitHub
# identity distinct from whatever account this machine's own tooling
# writes as) for it to be delivered. This repo is public, so anyone can
# post a **[INSTINCT]**-marked comment; the author check is the only real
# boundary. If INSTINCT_GH_USER is ever unset or equal to the account this
# script's own GH_TOKEN authenticates as, this script refuses to run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WIRE_DIR="$REPO_ROOT/.instinct-wire"
CONFIG_FILE="$WIRE_DIR/config"
STATE_FILE="$WIRE_DIR/state"
INBOX_FILE="$WIRE_DIR/inbox.md"
PID_FILE="$WIRE_DIR/watcher.pid"

mkdir -p "$WIRE_DIR"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "BLOCKED: $CONFIG_FILE not found. Create it with REPO, ISSUE_NUMBER, POLL_INTERVAL_SECONDS, INSTINCT_GH_USER." >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$CONFIG_FILE"

: "${REPO:?REPO must be set in .instinct-wire/config, e.g. talyaak/gd-pipeline}"
: "${ISSUE_NUMBER:?ISSUE_NUMBER must be set in .instinct-wire/config}"
: "${POLL_INTERVAL_SECONDS:=45}"
: "${INSTINCT_GH_USER:?INSTINCT_GH_USER must be set in .instinct-wire/config -- the dedicated Instinct GitHub account, never the same account this machine writes as}"

if ! command -v gh >/dev/null 2>&1; then
  echo "BLOCKED: gh CLI not found on PATH." >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "BLOCKED: jq not found on PATH (used to parse comment JSON)." >&2
  exit 1
fi

SELF_USER="$(gh api user --jq '.login' 2>/dev/null || true)"
if [ -z "$SELF_USER" ]; then
  echo "BLOCKED: could not resolve the authenticated gh user (check GH_TOKEN)." >&2
  exit 1
fi
if [ "$SELF_USER" = "$INSTINCT_GH_USER" ]; then
  echo "BLOCKED: INSTINCT_GH_USER ($INSTINCT_GH_USER) is the SAME account this script's own gh auth resolves to ($SELF_USER)." >&2
  echo "This defeats the entire point of author-based filtering. Refusing to run." >&2
  exit 1
fi

log() {
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"
}

# Idempotent/resumable: last-seen comment ID is the only thing tracked.
# A restart replays nothing already recorded here, and never re-delivers
# a comment ID <= what's on disk, even if inbox.md itself were lost.
last_seen_id() {
  if [ -f "$STATE_FILE" ]; then
    cat "$STATE_FILE"
  else
    echo 0
  fi
}

echo $$ > "$PID_FILE"
log "watcher started (pid $$), repo=$REPO issue=$ISSUE_NUMBER interval=${POLL_INTERVAL_SECONDS}s instinct_user=$INSTINCT_GH_USER self=$SELF_USER"

backoff=0
while true; do
  RESPONSE_FILE="$(mktemp)"
  if ! gh api --method GET "repos/$REPO/issues/$ISSUE_NUMBER/comments?per_page=100" > "$RESPONSE_FILE" 2>"$RESPONSE_FILE.err"; then
    if grep -qiE '403|429|rate limit' "$RESPONSE_FILE.err"; then
      backoff=$(( backoff == 0 ? POLL_INTERVAL_SECONDS : backoff * 2 ))
      backoff=$(( backoff > 900 ? 900 : backoff ))
      log "rate-limited or forbidden, backing off ${backoff}s: $(cat "$RESPONSE_FILE.err")"
      rm -f "$RESPONSE_FILE" "$RESPONSE_FILE.err"
      sleep "$backoff"
      continue
    else
      log "gh api call failed (non-rate-limit): $(cat "$RESPONSE_FILE.err")"
      rm -f "$RESPONSE_FILE" "$RESPONSE_FILE.err"
      sleep "$POLL_INTERVAL_SECONDS"
      continue
    fi
  fi
  backoff=0

  SEEN="$(last_seen_id)"
  MAX_SEEN="$SEEN"

  # Iterate comments in ascending id order, deliver only unseen ones.
  while IFS=$'\t' read -r cid cauthor cbody churl; do
    [ -z "$cid" ] && continue
    if [ "$cid" -le "$SEEN" ]; then
      continue
    fi
    if [ "$cid" -gt "$MAX_SEEN" ]; then
      MAX_SEEN="$cid"
    fi

    if [ "$cauthor" != "$INSTINCT_GH_USER" ]; then
      log "skip comment $cid: author=$cauthor (not $INSTINCT_GH_USER)"
      continue
    fi
    # jq's @tsv escapes embedded tabs/newlines/backslashes as literal
    # two-char sequences to keep one record per line in this loop; restore
    # real newlines before using the body for real (marker check and
    # delivery), rather than leaving literal \n or collapsing to spaces.
    cbody_real="$(printf '%s' "$cbody" | sed 's/\\t/\t/g; s/\\n/\n/g; s/\\\\/\\/g')"

    if [[ "$cbody_real" != '**[INSTINCT]**'* ]]; then
      log "skip comment $cid: author matches but no [INSTINCT] marker (loop-prevention -- also blocks our own [CLAUDE] test posts)"
      continue
    fi

    {
      echo ""
      echo "---"
      echo "[INSTINCT WIRE - new direction, comment $churl]"
      echo "$cbody_real"
      echo "[Reply by posting a **[CLAUDE]** comment on the Instinct Wire issue]"
    } >> "$INBOX_FILE"
    log "delivered comment $cid to inbox"
  done < <(jq -r '.[] | [.id, .user.login, .body, .html_url] | @tsv' "$RESPONSE_FILE" 2>/dev/null)

  if [ "$MAX_SEEN" != "$SEEN" ]; then
    echo "$MAX_SEEN" > "$STATE_FILE"
  fi

  rm -f "$RESPONSE_FILE" "$RESPONSE_FILE.err"
  sleep "$POLL_INTERVAL_SECONDS"
done
