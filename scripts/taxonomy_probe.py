"""One-off diagnostic: actually play a batch of past gate-passing runs with real
Playwright automation (not vision, not a Claude Browser pane) and report, per game,
whether it visibly progresses past its start screen and whether score/state changes
over ~15s of simulated play. This is the taxonomy pass to find out WHY gate-passers
weren't fun/playable: frozen-at-start vs runs-but-flat vs genuinely fine.

Not part of the pipeline. Run manually: python scripts/taxonomy_probe.py <dir_of_html_files>
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

import http.server
import socketserver
import threading


def _serve_dir(directory: Path):
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(directory), **kw)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, port


def probe_one(page, url: str) -> dict:
    result = {"url": url}
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    page.goto(url, wait_until="networkidle", timeout=15000)
    time.sleep(0.5)
    shot_before = page.screenshot()

    # Try the standard playable-ad start gestures: click center, then Space, then a
    # generic pointerdown -- covers "press space to start" / "click/tap to start" games.
    page.mouse.click(400, 225)
    page.keyboard.press("Space")
    time.sleep(0.3)
    page.mouse.down()
    page.mouse.up()
    time.sleep(1.0)

    shot_after_start = page.screenshot()
    started_changed = shot_before != shot_after_start

    # Simulate ~6s of actual play: alternate movement keys + occasional clicks.
    for key in ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Space", "d", "a", "w"]:
        page.keyboard.down(key)
        time.sleep(0.15)
        page.keyboard.up(key)
        page.mouse.click(400 + (hash(key) % 100 - 50), 225)
        time.sleep(0.25)

    shot_after_play = page.screenshot()
    play_changed = shot_after_start != shot_after_play

    result["started_changed_from_click_space"] = started_changed
    result["visibly_changed_during_6s_play"] = play_changed
    result["console_errors"] = console_errors[:5]

    Path("/tmp/taxonomy_shots").mkdir(exist_ok=True)
    stem = Path(url).name.replace("/", "_").replace(":", "_")
    Path(f"/tmp/taxonomy_shots/{stem}_before.png").write_bytes(shot_before)
    Path(f"/tmp/taxonomy_shots/{stem}_after_start.png").write_bytes(shot_after_start)
    Path(f"/tmp/taxonomy_shots/{stem}_after_play.png").write_bytes(shot_after_play)

    return result


def main():
    directory = Path(sys.argv[1])
    html_files = sorted(directory.glob("*.html"))
    httpd, port = _serve_dir(directory)

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for f in html_files:
            page = browser.new_page(viewport={"width": 800, "height": 450})
            url = f"http://127.0.0.1:{port}/{f.name}"
            try:
                r = probe_one(page, url)
            except Exception as e:
                r = {"url": url, "error": str(e)}
            results.append(r)
            page.close()
        browser.close()
    httpd.shutdown()

    for r in results:
        print("=" * 70)
        print(r.get("url"))
        if "error" in r:
            print("  ERROR:", r["error"])
            continue
        print("  started_changed_from_click_space:", r["started_changed_from_click_space"])
        print("  visibly_changed_during_6s_play:", r["visibly_changed_during_6s_play"])
        if r["console_errors"]:
            print("  console_errors:", r["console_errors"])


if __name__ == "__main__":
    main()
