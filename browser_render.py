"""Draws the reel's overlays (captions, hook, looks) with a real browser, so any font, card or animation
the editor preview shows comes out identically in the finished video.

studio/render.html + studio/stage.js draw one moment at a time; this module steps through the reel frame by
frame, captures each changed frame as a transparent PNG and hands the stream to ffmpeg, which lays it over
the cut video. Needs `pip install playwright` and Edge or Chrome (already on Windows and most Macs).
"""
import base64
import os
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer


class Unavailable(Exception):
    """The browser engine can't run here (playwright or a browser is missing)."""


def _launch(pw):
    tries = []
    if os.environ.get("REEL_BROWSER"):
        tries.append({"executable_path": os.environ["REEL_BROWSER"]})
    tries += [{"channel": "msedge"}, {"channel": "chrome"}, {}]
    errors = []
    for kw in tries:
        try:
            return pw.chromium.launch(headless=True, **kw)
        except Exception as e:  # noqa: BLE001 - try the next browser
            errors.append(str(e).splitlines()[0])
    raise Unavailable("no browser found (looked for Edge, Chrome, and Playwright's own Chromium)")


@contextmanager
def _server():
    """A private copy of the studio server on a free port, to serve stage.js, fonts and project images."""
    import studio
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), studio.make_handler(studio.App()))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


@contextmanager
def stage(payload, scale=1.0):
    """Open the render page. Yields shoot(t, **opts) -> PNG bytes, or None when nothing changed since the
    previous call (the caller repeats its last frame)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise Unavailable("playwright is not installed (pip install playwright)")
    with _server() as base, sync_playwright() as pw:
        browser = _launch(pw)
        try:
            size = {"width": round(1080 * scale), "height": round(1920 * scale)}
            page = browser.new_page(viewport=size, device_scale_factor=1)
            page.goto(base + "/studio/render.html")
            page.evaluate("([p, z]) => init(p, z)", [payload, scale])
            cdp = page.context.new_cdp_session(page)
            cdp.send("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})

            def shoot(t, **opts):
                changed = page.evaluate("([t, o]) => frame(t, o)", [t, opts])
                if not changed:
                    return None
                shot = cdp.send("Page.captureScreenshot", {"format": "png", "optimizeForSpeed": True})
                return base64.b64decode(shot["data"])

            yield shoot
        finally:
            browser.close()


def frames(shoot, total, fps, size, on_progress=None, **opts):
    """Yield one raw RGBA frame of `size` (w, h) per frame of the reel, repeating the previous one while
    nothing moves.

    Raw pixels rather than the PNGs themselves: the browser writes a fully covered frame (a full-screen
    card) as RGB and the rest as RGBA, and ffmpeg ends the stream when the format changes mid-way."""
    import io
    from PIL import Image
    n = max(1, round(total * fps))
    raw = None
    for i in range(n):
        # the first frame is always captured: the page may still hold the picture from a previous pass
        png = shoot(i / fps, force=(i == 0), **opts)
        if png is not None:
            im = Image.open(io.BytesIO(png)).convert("RGBA")
            raw = (im if im.size == tuple(size) else im.resize(tuple(size))).tobytes()
        if on_progress and i % 15 == 0:
            on_progress(i / n)
        yield raw
