"""Configuration for the Alibaba Scraper. Everything can be set with an
environment variable; the defaults work out of the box on a laptop.

    PORT              port the API listens on (default 8000)
    ALIBABA_PROXY     proxy URL for every request, e.g. http://user:pass@host:port
                      (default: none — direct connection). Alibaba's bot
                      protection is per-IP; if you start seeing "blocked the
                      request" errors, put a residential proxy here.
    ALIBABA_CACHE     "1" caches responses in memory for the TTL in
                      alibaba/cache_config.py (default off: every call is live)
    BROWSER_HEADLESS  "1" runs the supplier-search browser headless
                      (default: headed — a visible Chrome passes Alibaba's
                      checks more reliably; on a server use `xvfb-run`)
    BROWSER_CHANNEL   "chrome" to use an installed Google Chrome, "chromium"
                      for the bundled browser (default: chrome if installed,
                      else chromium)
    ALIBABA_DEBUG_DIR directory to dump raw punished/unparsable responses to

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

# Proxy for every curl_cffi request AND the supplier-search browser.
ALIBABA_PROXY = os.environ.get("ALIBABA_PROXY") or None
# With a proxy set, rebuild the connection after this many requests so a
# rotating provider hands out a fresh exit IP (harmless on a sticky one).
# Ignored without a proxy — a direct connection has nothing to rotate.
ALIBABA_REQUESTS_PER_EXIT = 30

CACHE_ENABLED = os.environ.get("ALIBABA_CACHE", "0").lower() in ("1", "true", "yes")

BROWSER_HEADLESS = os.environ.get("BROWSER_HEADLESS", "0").lower() in ("1", "true", "yes")
BROWSER_CHANNEL = os.environ.get("BROWSER_CHANNEL") or None

# No browser pools here: supplier search uses the single browser in
# browser.py; everything else is plain HTTP.
CHROME_POOLS = {}


def alibaba_proxy():
    """Proxy URL for one connection (None = direct)."""
    return ALIBABA_PROXY


# ---- added by the sync: defaults for a direct run ----
ALIBABA_BROWSER_SLOTS = 1
ALIBABA_POOL_PROXY_COUNTRY = None
def burst_slots(share):
    return share


def exit_geo(proxy, timeout=12):
    """Geo of a proxy's exit IP, looked up THROUGH the proxy (ip-api.com, free
    tier, keyed per exit IP so the quota is never shared). Returns the dict
    {countryCode, regionName, city, timezone, query} or None on any failure —
    callers keep their configured/system timezone then."""
    try:
        import requests
        r = requests.get(
            "http://ip-api.com/json/?fields=status,countryCode,regionName,city,timezone,query",
            proxies={"http": proxy, "https": proxy}, timeout=timeout)
        d = r.json()
        if d.get("status") == "success" and d.get("timezone"):
            return d
    except Exception:
        pass
    return None


def residential_proxy(country=None, states=None):
    return None

