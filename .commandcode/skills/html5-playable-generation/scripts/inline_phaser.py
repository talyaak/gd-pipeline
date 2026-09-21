#!/usr/bin/env python3
"""Create standalone HTML5 playable with Phaser inlined.

Usage:
    python inline_phaser.py generated_game.html [-o output.html]
"""

import sys
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Inline Phaser into generated game HTML")
    parser.add_argument("input", help="Input HTML file (without Phaser)")
    parser.add_argument("-o", "--output", help="Output file (default: input_standalone.html)")
    parser.add_argument("--phaser", help="Path to phaser.min.js (default: ../pipeline/vendor/phaser.min.js)")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        return 1
    
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_stem(input_path.stem + "_standalone")
    
    if args.phaser:
        phaser_path = Path(args.phaser)
    else:
        # Default relative to this script
        script_dir = Path(__file__).parent
        phaser_path = script_dir.parent.parent / "vendor" / "phaser.min.js"
    
    if not phaser_path.exists():
        print(f"Error: Phaser not found at {phaser_path}", file=sys.stderr)
        print("Download with: curl -sL https://cdn.jsdelivr.net/npm/phaser@3.80.1/dist/phaser.min.js -o pipeline/vendor/phaser.min.js", file=sys.stderr)
        return 1
    
    html = input_path.read_text(encoding="utf-8")
    phaser_js = phaser_path.read_text(encoding="utf-8")
    
    # Inject Phaser before </head> or at start of <body>
    if "</head>" in html:
        html = html.replace("</head>", f"<script>{phaser_js}</script></head>")
    else:
        html = html.replace("<body>", f"<body><script>{phaser_js}</script>")
    
    output_path.write_text(html, encoding="utf-8")
    print(f"Created standalone: {output_path} ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())