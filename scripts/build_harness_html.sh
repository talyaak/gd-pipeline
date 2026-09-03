#!/usr/bin/env bash
# Concatenates vendored Phaser + the shared Juice toolkit + one harness's game
# code into a single self-contained HTML file (no external requests, no
# build step) -- same wrapper every harness/*.html uses.
set -euo pipefail
cd "$(dirname "$0")/.."

NAME="$1"       # e.g. match_3
TITLE="$2"      # e.g. "Prism Cascade - Harness"

{
  echo '<!DOCTYPE html>'
  echo "<html><head><meta charset=\"utf-8\"><title>${TITLE}</title>"
  echo '<style>html,body{margin:0;background:#0a0a18;overflow:hidden;display:flex;align-items:center;justify-content:center;height:100%;}canvas{display:block;}</style>'
  echo '</head><body>'
  echo '<script>'
  cat pipeline/vendor/phaser.min.js
  echo
  cat pipeline/vendor/juice.js
  echo
  cat "harness/${NAME}.game.js"
  echo '</script>'
  echo '</body></html>'
} > "harness/${NAME}.html"

wc -c "harness/${NAME}.html"
