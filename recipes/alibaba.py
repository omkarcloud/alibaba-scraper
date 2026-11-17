"""Alibaba supplier search (/trade/search?tab=supplier): fingerprint-gated by
the baxia punish slider. A real Chrome renders it on a TOP-LEVEL navigation;
curl and even same-origin in-page fetch are punished (alibaba/fetch.py
_gated_get, validated 2026-09-14). So this is a navigate-mode fetch: GKE
sends the target URL, the box navigates and returns the DOM. Warm-up parks
on a plain keyword search, then proves the gated surface renders
(window._PAGE_DATA_). Egress: whatever GKE sends (residential US today).
Punish sticks to the IP for ~250 s, so a punished browser is dropped."""
from browser_worker.types import PageFetch, RecipeError

BASE = "https://www.alibaba.com"
PUNISH_MARKERS = ("_____tmd_____", "<punish-component", "x5secdata")
WARM_SEED_URL = f"{BASE}/trade/search?SearchText=bluetooth+speaker"
WARM_VALIDATE_URL = f"{BASE}/trade/search?SearchText=bluetooth+speaker&tab=supplier"


def _punished(text):
    head = (text or "")[:120000]
    return any(m in head for m in PUNISH_MARKERS)


class AlibabaSupplierSearch(PageFetch):
    name = "alibaba"
    headless = False
    variants = {"": WARM_SEED_URL}
    mode = "navigate"
    nav_mode = "blocked"
    challenge_markers = PUNISH_MARKERS
    park_url = BASE + "/robots.txt"
    idle_seconds = 300
    max_browsers = 2

    def warm(self, driver, variant):
        res = driver.nav(WARM_SEED_URL, referer="https://www.google.com/", mode="blocked",
                         challenge_markers=PUNISH_MARKERS) or {}
        if _punished(res.get("html") or ""):
            raise RecipeError("alibaba: warm-up seed search punished")
        res = driver.nav(WARM_VALIDATE_URL, referer=WARM_SEED_URL, mode="blocked",
                         challenge_markers=PUNISH_MARKERS) or {}
        if "_PAGE_DATA_" not in (res.get("html") or ""):
            raise RecipeError("alibaba: warm-up supplier search did not render")

    def fetch_one(self, driver, url, method, headers, body):
        out = super().fetch_one(driver, url, "GET", headers or {"referer": BASE + "/"}, None)
        if out["status"] in (403, 429) or _punished(out["body"]):
            raise RecipeError(f"alibaba: gated page punished (status={out['status']})")
        if not (out["body"] or "").strip():
            raise RecipeError(f"alibaba: empty page for {url}")
        return out


RECIPE = AlibabaSupplierSearch
