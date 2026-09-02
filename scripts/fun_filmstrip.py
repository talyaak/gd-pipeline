"""One-off: play each game for a real ~15-20s session with genre-appropriate input
(not just enough to trigger a start-screen transition) and save a filmstrip of
screenshots so a human/agent can actually judge feel -- difficulty ramp, variety,
responsiveness, juice -- not just "did it start". Manual diagnostic, not pipeline code.

Usage: python scripts/fun_filmstrip.py <html_file> <genre>
genre in {shmup, runner, tower, match3}
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
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def play_shmup(page):
    page.mouse.click(400, 225)
    page.keyboard.press("Space")
    yield
    for i in range(20):
        key = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"][i % 4]
        page.keyboard.down(key)
        time.sleep(0.2)
        page.keyboard.up(key)
        if i % 6 == 0:
            page.keyboard.press("z")
        yield


def play_runner(page):
    page.mouse.click(400, 225)
    page.keyboard.press("Space")
    yield
    for i in range(30):
        key = ["a", "d", "Space", "d", "a", "Space"][i % 6]
        page.keyboard.press(key)
        time.sleep(0.55)
        yield


def play_tower(page):
    page.mouse.click(400, 225)
    yield
    for x, y in [(300, 200), (350, 250), (400, 200)]:
        page.mouse.click(x, y)
        yield
        page.mouse.click(x, y + 20)
        yield
    page.mouse.click(400, 400)
    yield


def play_match3(page):
    page.mouse.click(400, 225)
    yield
    for i in range(10):
        x1, y1 = 300 + (i % 5) * 40, 200 + (i % 3) * 40
        page.mouse.click(x1, y1)
        yield
        page.mouse.click(x1 + 40, y1)
        yield


GENRES = {"shmup": play_shmup, "runner": play_runner, "tower": play_tower, "match3": play_match3}


def main():
    html_path = Path(sys.argv[1])
    genre = sys.argv[2]
    play_fn = GENRES[genre]

    directory = html_path.parent
    httpd, port = _serve_dir(directory)
    url = f"http://127.0.0.1:{port}/{html_path.name}"

    out_dir = Path("/tmp/fun_filmstrip") / html_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 800, "height": 450})
        page.goto(url, wait_until="networkidle", timeout=15000)
        time.sleep(0.3)
        page.screenshot(path=str(out_dir / "00_initial.png"))

        # Single-threaded: interleave play steps (generator) with screenshots.
        # Playwright's sync API is not thread-safe, so play and capture must
        # happen on the same thread/greenlet.
        gen = play_fn(page)
        i = 1
        start = time.time()
        last_shot = 0.0
        for _ in gen:
            now = time.time() - start
            if now - last_shot >= 1.5:
                try:
                    page.screenshot(path=str(out_dir / f"{i:02d}_t{now:.1f}s.png"))
                except Exception:
                    pass
                i += 1
                last_shot = now
            if now > 18:
                break
        page.screenshot(path=str(out_dir / "99_final.png"))
        browser.close()
    httpd.shutdown()
    print(f"Filmstrip saved to {out_dir}")


if __name__ == "__main__":
    main()
