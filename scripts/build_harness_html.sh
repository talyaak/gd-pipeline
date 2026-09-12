#!/usr/bin/env bash
# Concatenates vendored Phaser + the shared Juice toolkit + one harness's game
# code into a single self-contained HTML file (no external requests, no
# build step) -- same wrapper every harness/*.html uses.
set -euo pipefail
cd "$(dirname "$0")/.."

NAME="$1"       # e.g. match_3
TITLE="$2"      # e.g. "Prism Cascade - Harness"
SRC_GAME_JS="${3:-harness/${NAME}.game.js}"  # optional override
INCLUDE_MRAID="${4:-false}"  # optional: include mraid.js (for reskin/ad builds)

{
  echo '<!DOCTYPE html>'
  echo "<html><head><meta charset=\"utf-8\">"
  echo '<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">'
  echo "<title>${TITLE}</title>"
  echo '<style>:root{--safe-top:env(safe-area-inset-top,0px);--safe-right:env(safe-area-inset-right,0px);--safe-bottom:env(safe-area-inset-bottom,0px);--safe-left:env(safe-area-inset-left,0px);}html,body{margin:0;background:#0a0a18;overflow:hidden;height:100%;width:100%;position:fixed;touch-action:none;}#game-root{width:100%;height:100%;display:flex;align-items:center;justify-content:center;}canvas{display:block;touch-action:none;}</style>'
  echo '</head><body>'
  echo '<div id="game-root"></div>'
  echo '<script>'
  cat pipeline/vendor/phaser.min.js
  echo
  cat pipeline/vendor/juice.js
  echo
  cat pipeline/vendor/art.js
  echo
  cat pipeline/vendor/ui.js
  echo
  cat pipeline/vendor/particle.js
  echo
  cat pipeline/vendor/visual_asset_engine.js
  echo
  if [ "$INCLUDE_MRAID" = "true" ]; then
    cat pipeline/vendor/mraid.js
    echo
  fi
  cat "${SRC_GAME_JS}"
  echo '</script>'
  echo '</body></html>'
} > "harness/${NAME}.html"

wc -c "harness/${NAME}.html"
