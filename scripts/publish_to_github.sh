#!/usr/bin/env bash
# Publishes /workspace to https://github.com/talyaak/gd-pipeline (main), with
# the same sanitization applied every time -- NEVER push /workspace directly
# to that remote, its full history contains business-strategy docs that must
# never appear there (see the doc list below, and the human's own explicit
# instruction the first time this was done: "make sure nothing sensitive
# goes up there, including my plans to turn this into a playable ad
# factory -- this is secret business logic").
#
# What this strips, and why:
#   - The 8 strategy docs below: removed from EVERY commit in history, not
#     just the latest snapshot (git-filter-repo --path --invert-paths).
#     Editing them out of a fresh commit is NOT enough -- anyone who clones
#     could still find them in old commits.
#   - Commit MESSAGES that name-drop those doc files (e.g. "(ROADMAP.md Day
#     6 prep)") -- these describe the same business logic in a different
#     place. Stripped via --message-callback.
#   - Every commit's author/committer name+email -- rewritten to talyaak's
#     GitHub noreply identity via --name-callback/--email-callback, since
#     this repo is public and commits should attribute to the human, not
#     to whatever local identity (personal email, Hermes cron identity,
#     etc.) actually made the commit.
#
# This all happens in a throwaway clone under /tmp -- the real /workspace
# repo (full history, untouched) is never modified by this script.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_URL="https://github.com/talyaak/gd-pipeline.git"
FILTER_REPO="/home/harness/.hermes/tools/git-filter-repo"
WORK_DIR="$(mktemp -d /tmp/gd-pipeline-publish.XXXXXX)"
CLONE_DIR="$WORK_DIR/clean"

# Files that must never appear anywhere in the pushed history.
STRIP_FILES=(
  STRATEGY.md
  ONDEMAND_GENERATION.md
  ROADMAP.md
  HANDOVER.md
  PROJECT_HISTORY.md
  CRITIQUE_REPORT.md
  LESSONS_LEARNED.md
  HERMES_CRON_LOG.md
)

if [ ! -f "$FILTER_REPO" ]; then
  echo "BLOCKED: git-filter-repo not found at $FILTER_REPO." >&2
  echo "Do not fall back to a plain 'git push' -- that would push the" >&2
  echo "unsanitized history with the strategy docs in it. Fetch it first:" >&2
  echo "  mkdir -p /home/harness/.hermes/tools && curl -sL https://raw.githubusercontent.com/newren/git-filter-repo/main/git-filter-repo -o $FILTER_REPO && chmod +x $FILTER_REPO" >&2
  exit 1
fi

echo "== cloning $REPO_ROOT into throwaway workdir =="
git clone --no-local "$REPO_ROOT" "$CLONE_DIR"
cd "$CLONE_DIR"

echo "== stripping strategy docs from all history =="
path_args=()
for f in "${STRIP_FILES[@]}"; do
  path_args+=(--path "$f")
done
python3 "$FILTER_REPO" "${path_args[@]}" --invert-paths --force

echo "== stripping strategy-doc filename references from commit messages =="
python3 "$FILTER_REPO" --message-callback '
import re
msg = message.decode("utf-8", errors="replace")
doc_names = r"ONDEMAND_GENERATION\.md|ROADMAP\.md|STRATEGY\.md|HANDOVER\.md|CRITIQUE_REPORT\.md|LESSONS_LEARNED\.md|HERMES_CRON_LOG\.md|PROJECT_HISTORY\.md"
msg = re.sub(r"\s*\([^)]*(?:" + doc_names + r")[^)]*\)", "", msg)
msg = re.sub(doc_names, "internal notes", msg)
msg = re.sub(r"[ \t]+\n", "\n", msg)
msg = re.sub(r"  +", " ", msg)
return msg.encode("utf-8")
' --force

echo "== rewriting every commit author/committer to talyaak =="
python3 "$FILTER_REPO" \
  --name-callback 'return b"talyaak"' \
  --email-callback 'return b"talyaak@users.noreply.github.com"' \
  --force

echo "== verifying: none of the stripped files/messages/email survive =="
for f in "${STRIP_FILES[@]}"; do
  if [ "$(git log --all --oneline -- "$f" | wc -l)" -ne 0 ]; then
    echo "BLOCKED: $f still present in history after filtering. Aborting push." >&2
    exit 1
  fi
done
if git log --all --format="%ae" | grep -q "tal.jacobov@gmail.com"; then
  echo "BLOCKED: real personal email still present after filtering. Aborting push." >&2
  exit 1
fi
other_identities="$(git log --all --format='%an <%ae>%n%cn <%ce>' | sort -u | grep -v '^talyaak <talyaak@users.noreply.github.com>$' || true)"
if [ -n "$other_identities" ]; then
  echo "BLOCKED: found non-talyaak author/committer identities after filtering:" >&2
  echo "$other_identities" >&2
  exit 1
fi
echo "verification passed."

echo "== pushing sanitized history to $REMOTE_URL (main, force) =="
git remote add origin "$REMOTE_URL"
git branch -M main
git push --force origin main

echo "== cleaning up throwaway workdir =="
cd /
rm -rf "$WORK_DIR"

echo "Done. Check CI: https://github.com/talyaak/gd-pipeline/actions"
