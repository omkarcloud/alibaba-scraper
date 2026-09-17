"""One real browser (patchright Chrome) for the single Alibaba surface that
is fingerprint-gated: supplier search. Everything else in this project is
plain HTTP; this module only wakes up on the first /suppliers/search call.

Why a browser: /trade/search?tab=supplier answers curl with Alibaba's baxia
slider captcha no matter which cookies you replay — only a top-level
navigation by a real Chrome renders it. So the page is loaded by Chrome and
its HTML handed back; the parsers are the same as for every other page.

Playwright objects belong to the thread that created them, so the browser
lives on one owner thread and requests queue up on it (one navigation at a
time, ~3-5 s each). A punished or broken browser is retired and relaunched
on the next call.
"""
import os
import queue
import shutil
import sys
import tempfile
import threading
import time
from urllib.parse import urlparse

import config

SETTLE_MS = 8000          # networkidle wait after domcontentloaded
GOTO_TIMEOUT_MS = 60000
CALL_TIMEOUT = 120        # seconds a caller waits for the owner thread

_display = None


class BrowserError(RuntimeError):
    pass


def _ensure_display():
    """On a headless Linux box (a server, a Docker container) a headed Chrome
    needs an X display. If none is set, start our own Xvfb and point DISPLAY
    at it — so `python run.py` works the same in a container as on a laptop.
    Returns True when a display is available, False to fall back to headless."""
    global _display
    if os.environ.get("DISPLAY"):
        return True
    if not sys.platform.startswith("linux"):
        return True                      # macOS / Windows have their own
    if _display and _display.poll() is None:
        return True
    if not shutil.which("Xvfb"):
        print("browser: no DISPLAY and no Xvfb installed, running headless "
              "(install xvfb, or set BROWSER_HEADLESS=1 to silence this)")
        return False
    import subprocess
    for num in range(99, 110):
        if os.path.exists(f"/tmp/.X11-unix/X{num}"):
            continue
        proc = subprocess.Popen(["Xvfb", f":{num}", "-screen", "0", "1280x1024x24", "-nolisten", "tcp"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            if os.path.exists(f"/tmp/.X11-unix/X{num}"):
                _display = proc
                os.environ["DISPLAY"] = f":{num}"
                return True
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        proc.terminate()
    print("browser: could not start Xvfb, running headless")
    return False


def _proxy_dict(url):
    u = urlparse(url)
    out = {"server": f"{u.scheme or 'http'}://{u.hostname}:{u.port}"}
    if u.username:
        out["username"] = u.username
    if u.password:
        out["password"] = u.password
    return out


class _Browser:
    def __init__(self):
        self._jobs = queue.Queue()
        self._thread = None
        self._primed = False
        self._lock = threading.Lock()

    # ---- owner thread ----------------------------------------------------
    def _main(self, started):
        from patchright.sync_api import sync_playwright

        pw = ctx = page = None
        profile = tempfile.mkdtemp(prefix="alibaba-browser-")
        try:
            pw = sync_playwright().start()
            headless = config.BROWSER_HEADLESS or not _ensure_display()
            kwargs = dict(user_data_dir=profile, headless=headless, no_viewport=True,
                          locale="en-US", args=["--lang=en-US"])
            if config.alibaba_proxy():
                kwargs["proxy"] = _proxy_dict(config.alibaba_proxy())
            channels = [config.BROWSER_CHANNEL] if config.BROWSER_CHANNEL else ["chrome", None]
            last = None
            for channel in channels:
                try:
                    ctx = pw.chromium.launch_persistent_context(
                        **({"channel": channel} if channel and channel != "chromium" else {}), **kwargs)
                    break
                except Exception as e:      # no Google Chrome installed -> bundled chromium
                    last = e
            if ctx is None:
                raise BrowserError(f"could not launch a browser: {last}")
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            started.put(None)
        except Exception as e:
            started.put(e)
            self._cleanup(pw, ctx, profile)
            return
        while True:
            fn, reply = self._jobs.get()
            if fn is None:
                break
            try:
                reply.put((True, fn(page)))
            except Exception as e:
                reply.put((False, e))
        self._cleanup(pw, ctx, profile)

    @staticmethod
    def _cleanup(pw, ctx, profile):
        for closer in ((ctx.close if ctx else None), (pw.stop if pw else None)):
            try:
                if closer:
                    closer()
            except Exception:
                pass
        shutil.rmtree(profile, ignore_errors=True)

    # ---- public --------------------------------------------------------------
    def _ensure(self):
        if self._thread and self._thread.is_alive():
            return
        started = queue.Queue()
        self._thread = threading.Thread(target=self._main, args=(started,), daemon=True, name="alibaba-browser")
        self._thread.start()
        err = started.get(timeout=CALL_TIMEOUT)
        if err is not None:
            self._thread = None
            raise BrowserError(str(err))
        self._primed = False

    def call(self, fn):
        with self._lock:
            self._ensure()
            reply = queue.Queue()
            self._jobs.put((fn, reply))
            ok, value = reply.get(timeout=CALL_TIMEOUT)
        if not ok:
            raise BrowserError(str(value))
        return value

    def navigate(self, url, referer=None):
        """Top-level navigation; returns (html, status)."""
        def _do(page):
            resp = page.goto(url, referer=referer, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
            try:
                page.wait_for_load_state("networkidle", timeout=SETTLE_MS)
            except Exception:
                pass
            return page.content(), (resp.status if resp else None)
        return self.call(_do)

    @property
    def primed(self):
        return self._primed and self._thread is not None and self._thread.is_alive()

    def mark_primed(self):
        self._primed = True

    def retire(self):
        """Close the browser; the next call launches a fresh one."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                self._jobs.put((None, None))
                self._thread.join(timeout=30)
            self._thread = None
            self._primed = False


BROWSER = _Browser()
