"""
Shared fixtures/constants/helpers for the real-device farm_idle test suite
(split out of the former monolithic tests/test_farm_idle_real_device.py).

Not itself a test module -- imported explicitly by test_farm_idle_camera.py,
test_farm_idle_market.py, test_farm_idle_helper.py, test_farm_idle_hud.py,
and test_farm_idle_economy.py. Deliberately not tests/conftest.py: plain
constants and helper functions placed there are not auto-discovered as
importable globals by pytest (only fixtures/hooks are), so an explicit
import is required in each module that uses these names.
"""
import struct
import zlib
from pathlib import Path

HARNESS_DIR = Path(__file__).parent.parent / "harness"

# Real short-Safari-chrome-accounted-for viewports -- these are the sizes
# that actually surfaced the original real-device defects, deliberately NOT
# the taller ~390x844 emulated size used throughout the prior review cycle.
SHORT_VIEWPORTS = [
    (390, 650, "iPhone_effective_short"),
    (414, 700, "iPhone_11_short_chrome"),
    (360, 615, "Galaxy_short_chrome"),
]

# Included as a contrast case: the taller viewport prior testing used, where
# the old bug happened to (barely) not trigger. Fixes must keep working
# here too, not just at the short sizes.
TALL_VIEWPORT = (390, 844, "iPhone_12_tall_contrast")


def _safe_insets_for(viewport_name):
    if "iPhone" in viewport_name:
        return {"top": 44, "right": 0, "bottom": 34, "left": 0}
    if "Galaxy" in viewport_name:
        return {"top": 0, "right": 0, "bottom": 24, "left": 0}
    return {"top": 0, "right": 0, "bottom": 0, "left": 0}


def _read_pixel_region_via_screenshot(page, screen_x, screen_y, width, height):
    """Read the RGB colors actually composited in the (width x height) region
    at (screen_x, screen_y) via a Playwright screenshot clip, decoding the
    returned PNG with stdlib only. Needed because farm_idle's canvas uses
    Phaser's default WebGL renderer with preserveDrawingBuffer left at its
    default `false`: canvas.getContext("2d") returns null on an
    already-WebGL canvas, and both gl.readPixels() and canvas.toDataURL()
    read back all-black regardless of real content or added waits, since
    the browser is free to -- and empirically does -- clear the drawing
    buffer right after compositing each frame. A screenshot captures the
    compositor's actual output instead, sidestepping the WebGL buffer
    entirely.

    Returns a list of `height` rows, each a list of `width` (r, g, b) tuples.
    """
    png_bytes = page.screenshot(clip={"x": screen_x, "y": screen_y, "width": width, "height": height})
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos = 8
    png_width = bit_depth = color_type = None
    idat = b""
    while pos < len(png_bytes):
        length = struct.unpack(">I", png_bytes[pos:pos + 4])[0]
        ctype = png_bytes[pos + 4:pos + 8]
        data = png_bytes[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            png_width, png_height, bit_depth, color_type = struct.unpack(">IIBB", data[:10])
        elif ctype == b"IDAT":
            idat += data
        elif ctype == b"IEND":
            break
        pos += 8 + length + 4
    assert bit_depth == 8, f"unexpected PNG bit depth {bit_depth}"
    bpp = {2: 3, 6: 4}.get(color_type)
    assert bpp, f"unexpected PNG color type {color_type}"
    raw = zlib.decompress(idat)
    stride = png_width * bpp
    rows = []
    prior = bytearray(stride)  # PNG "previous scanline" for row 0 is all-zero
    offset = 0
    for _row in range(png_height):
        filt = raw[offset]
        line = bytearray(raw[offset + 1:offset + 1 + stride])
        if filt == 0:  # None
            pass
        elif filt == 1:  # Sub
            for i in range(len(line)):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + a) & 0xFF
        elif filt == 2:  # Up
            for i in range(len(line)):
                line[i] = (line[i] + prior[i]) & 0xFF
        elif filt == 3:  # Average
            for i in range(len(line)):
                a = line[i - bpp] if i >= bpp else 0
                b = prior[i]
                line[i] = (line[i] + (a + b) // 2) & 0xFF
        elif filt == 4:  # Paeth
            for i in range(len(line)):
                a = line[i - bpp] if i >= bpp else 0
                b = prior[i]
                c = prior[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        else:
            raise ValueError(f"unsupported PNG filter type {filt}")
        rows.append([tuple(line[i:i + 3]) for i in range(0, stride, bpp)])
        prior = line
        offset += 1 + stride
    return rows


def _read_pixel_via_screenshot(page, screen_x, screen_y):
    """Read the RGB color actually composited at a single (screen_x, screen_y)
    point. See _read_pixel_region_via_screenshot() for why a screenshot is
    used instead of canvas/WebGL pixel-read APIs.
    """
    return _read_pixel_region_via_screenshot(page, screen_x, screen_y, 1, 1)[0][0]


def _boot(page, viewport_name):
    """Common boot sequence: load harness, start game, apply safe insets."""
    html_path = HARNESS_DIR / "farm_idle.html"
    page.goto(f"file://{html_path.absolute()}")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("window.__GAME__ !== undefined", timeout=10000)
    page.wait_for_timeout(300)

    page.evaluate("() => { window.__GAME__.scene.scenes[0]._begin(); }")
    page.wait_for_timeout(100)

    insets = _safe_insets_for(viewport_name)
    page.evaluate("""
        () => {
            const root = document.documentElement;
            root.style.setProperty('--safe-top', '%dpx');
            root.style.setProperty('--safe-right', '%dpx');
            root.style.setProperty('--safe-bottom', '%dpx');
            root.style.setProperty('--safe-left', '%dpx');
            if (typeof updateSafeInsets === 'function') updateSafeInsets();
            const scene = window.__GAME__.scene.scenes[0];
            if (scene._layoutHUD) scene._layoutHUD();
        }
    """ % (insets["top"], insets["right"], insets["bottom"], insets["left"]))
    page.wait_for_timeout(100)