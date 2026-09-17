"""Alibaba.com transport. Plain curl_cffi for every open surface, one real
Chrome (browser.py) ONLY for the surface that is fingerprint-gated.

Validated 2026-09-14 (direct India egress and US residential proxy exits):

OPEN over plain curl_cffi (impersonate="chrome", no cookies, no browser):
  * /catalog/x_cid<id|0>?SearchText=..&page=..&<filters>  — keyword AND
    category product search WITH every filter/sort param (pricef/pricet,
    moqf/moqt, ta, sortType, country, reviewScore, freeSample,
    assessmentCompany, verifiedPro, halfTrust, overseaShipFrom, deliveryDay,
    companyAuthTag, productAuthTag). cid0 = all categories. Same
    window.__page__data_sse10._offer_list blob as /trade/search, 48/page,
    100 pages. Tolerated a 3-request burst from one IP. THIS is the product
    search surface — /trade/search is NOT: the same filter params there hit
    the baxia punish slider 100% cold, and even the plain
    /trade/search?SearchText= form was punished on 6/6 fresh US residential
    exits and after any 3-hit burst from one IP (the punish then sticks to
    the IP for ~250 s).
  * /product-detail/x_<id>.html — window.detailData (numeric id alone works).
  * <sub>.en.alibaba.com/ , /productlist-N.html[?SearchText=&sortType=],
    /company_profile/feedback.html — module-data attributes (URL-encoded
    JSON per shop module). company_profile.html / contactinfo.html are
    punished every time and are not used.
  * acs.h.alibaba.com mtop.alibaba.icbu.review.media.review — product AND
    store reviews (companyId alone works), standard _m_h5_tk handshake.
  * open-s.alibaba.com openservice/* (autocomplete, trending, OSS upload
    policy, imageSearchViewService = the image-search result list) and
    insights.alibaba.com gatewayService (category tree) — bare JSON. Image
    search therefore never needs the browser: upload via the signed OSS
    policy, then page the matches through the gateway (validated
    2026-09-14, 20 offers/page). The HTML /picture/search.htm page is
    fingerprint-gated AND renders zero offers server-side — unused.
  Currency: the sc_g_cfg_f cookie ("sc_b_currency=EUR") switches every price
  on catalog + product pages (validated USD/EUR/INR). Never send
  sc_b_site=US with it — the product page then renders "Product Not
  Available".

FINGERPRINT-GATED (one real Chrome, browser.py):
  * /trade/search?tab=supplier — supplier search (window._PAGE_DATA_).
    Every filter/sort param on /trade/search is gated the same way (and
    the catalog surface ignores tab=supplier), so this is the ONE surface
    the browser serves. A real Chrome passes it cold; replaying its cookies
    over curl_cffi is still punished (baxia keys on the TLS/JS fingerprint),
    and even a same-origin in-page fetch() is punished. Only a top-level
    NAVIGATION renders it, so browser.py navigates to the URL per request
    (~3-5 s). Everything else never touches the browser.

Proxy policy: direct by default (config.ALIBABA_PROXY = None). With a
rotating proxy set, every worker thread rebuilds its connection (= a new
exit) on the first punish — the punish sticks to an IP for minutes, so
retrying on the same exit is pointless.

Failure taxonomy:
  AlibabaUpstreamError  transport failure / 5xx — retryable
  AlibabaBlocked        baxia punish page / 403 / 429 — retryable on a new exit
  AlibabaBadRequest     upstream rejected the params — never retried
  AlibabaNotFound       product / store does not exist — never retried
"""
import hashlib
import json
import os
import re
import sys
import threading
import time
from urllib.parse import quote, urlencode

# Allow direct execution (python alibaba/<module>.py): flat imports resolve
# like under the server. Idempotent when imported normally.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError  # noqa: E402

BASE = "https://www.alibaba.com"
OPEN_S = "https://open-s.alibaba.com/openservice"
INSIGHTS = "https://insights.alibaba.com/openservice/gatewayService"
MTOP = "https://acs.h.alibaba.com/h5"
MTOP_APP_KEY = "12574478"
IMPERSONATE = "chrome"
PAGE_TIMEOUT = 45       # search pages run ~1MB
JSON_TIMEOUT = 20

PUNISH_MARKERS = ("_____tmd_____", "<punish-component", "x5secdata")
PAGE_HEADERS = {
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "accept-language": "en-US,en;q=0.9",
}
JSON_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "referer": f"{BASE}/",
    "origin": BASE,
}


class AlibabaUpstreamError(UpstreamError):
    """Transport failure or 5xx — retryable."""


class AlibabaBlocked(AlibabaUpstreamError, Blocked):
    """baxia punish page / 403 / 429 — retryable on a fresh exit."""


class AlibabaBadRequest(BadRequest):
    """Upstream rejected the params — never retried."""


class AlibabaNotFound(NotFound):
    """Product / store / page doesn't exist — never retried."""


def looks_punished(text):
    head = (text or "")[:120000]
    return any(m in head for m in PUNISH_MARKERS)


def dump_debug(name, text):
    """Write raw response text to $ALIBABA_DEBUG_DIR/<name>.txt for post-mortems."""
    dbg = os.environ.get("ALIBABA_DEBUG_DIR", "")
    if dbg and text:
        try:
            os.makedirs(dbg, exist_ok=True)
            with open(os.path.join(dbg, name + ".txt"), "w") as f:
                f.write(text)
        except OSError:
            pass


# ---- curl_cffi sessions (one per worker thread, one sticky exit each) -------
_local = threading.local()


def _session():
    """The thread's curl session. With a proxy configured the session holds
    one exit and is rebuilt (= a fresh exit from a rotating provider) after
    config.ALIBABA_REQUESTS_PER_EXIT requests or on the first punish."""
    sess = getattr(_local, "session", None)
    used = getattr(_local, "used", 0)
    limit = getattr(config, "ALIBABA_REQUESTS_PER_EXIT", 0) or 0
    if sess is not None and limit and used >= limit and config.alibaba_proxy():
        _drop_session()
        sess = None
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = config.alibaba_proxy()
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        _local.session = sess
        _local.used = 0
    _local.used = getattr(_local, "used", 0) + 1
    return sess


def _drop_session():
    """Close the thread's session so a punished exit / poisoned keep-alive dies."""
    sess = getattr(_local, "session", None)
    _local.session = None
    _local.used = 0
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _retrying(fn, retries=None):
    """Run fn() under the shared retry policy (AlibabaUpstreamError only). A
    block drops the session first so the retry leaves on a fresh exit."""
    attempts = config.MAX_RETRIES if retries is None else retries
    last = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except AlibabaUpstreamError as e:
            last = e
            _drop_session()
            if attempt < attempts:
                time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def currency_cookies(currency):
    """Cookie jar that renders prices in `currency` (3-letter ISO). None/"" ->
    the site default for the egress geo (INR from India, USD from the US)."""
    if not currency:
        return {}
    return {"sc_g_cfg_f": f"sc_b_currency={currency.upper()}"}


# ---- HTML pages ------------------------------------------------------------

def _page_get_once(url, referer, cookies):
    headers = dict(PAGE_HEADERS)
    headers["referer"] = referer or f"{BASE}/"
    try:
        resp = _session().get(url, headers=headers, cookies=cookies or None,
                              timeout=PAGE_TIMEOUT, allow_redirects=True)
    except Exception as e:
        raise AlibabaUpstreamError(f"request failed: {type(e).__name__}: {e}")
    text = resp.text or ""
    if resp.status_code in (404, 410):
        raise AlibabaNotFound(url)
    if resp.status_code == 400:
        raise AlibabaBadRequest(text[:200])
    if resp.status_code in (403, 429) or looks_punished(text):
        dump_debug("punished_page", text)
        raise AlibabaBlocked(f"alibaba punish page (HTTP {resp.status_code}) for {url}")
    if resp.status_code >= 500:
        raise AlibabaUpstreamError(f"HTTP {resp.status_code} for {url}")
    if str(resp.url).startswith("https://error.alibaba.com/"):
        raise AlibabaNotFound(url)
    return text, str(resp.url)


def fetch_page(url, referer=None, currency=None, cookies=None):
    """GET one alibaba.com HTML page over curl_cffi; returns (html, final_url).
    Retries transport errors and punishes (each retry on a fresh exit when a
    proxy country is configured); BadRequest/NotFound surface immediately.
    An empty 200 body is how a non-existent store subdomain answers."""
    jar = dict(currency_cookies(currency))
    if cookies:
        jar.update(cookies)
    html, final = _retrying(lambda: _page_get_once(url, referer, jar))
    if not html.strip():
        raise AlibabaNotFound(url)
    return html, final


# ---- JSON gateways (open-s / insights) ------------------------------------

def _json_get_once(url, params=None, data=None):
    try:
        if data is not None:
            resp = _session().post(url, data=data, headers=JSON_HEADERS,
                                   timeout=JSON_TIMEOUT)
        else:
            resp = _session().get(url, params=params, headers=JSON_HEADERS,
                                  timeout=JSON_TIMEOUT)
    except Exception as e:
        raise AlibabaUpstreamError(f"request failed: {type(e).__name__}: {e}")
    if resp.status_code in (403, 429):
        raise AlibabaBlocked(f"HTTP {resp.status_code} from {url}")
    if resp.status_code != 200:
        raise AlibabaUpstreamError(f"HTTP {resp.status_code} from {url}")
    try:
        return resp.json()
    except Exception:
        dump_debug("nonjson_gateway", resp.text)
        raise AlibabaUpstreamError(f"non-JSON response from {url}")


def fetch_json(url, params=None, data=None):
    """GET (or form-POST when `data` is given) a JSON gateway; returns the
    parsed body. Gateways answer {"code": 200, "data": ...}; a non-200 code
    is an upstream error (the gateways never 4xx on bad input, they answer an
    empty list)."""
    payload = _retrying(lambda: _json_get_once(url, params, data))
    if isinstance(payload, dict) and payload.get("code") not in (None, 200, "200"):
        raise AlibabaUpstreamError(f"gateway code {payload.get('code')}: {payload.get('msg')}")
    return payload


def open_service(name, **params):
    return fetch_json(f"{OPEN_S}/{name}", params=params)


def ensure_site_cookies():
    """Make sure the thread's session has visited www.alibaba.com (the `cna`
    cookie is only minted there — the open-s gateways set ali_apache_id /
    XSRF-TOKEN themselves, so those are no proof). Validated 2026-09-14: the
    image search gateway (imageSearchViewService) answers a session that
    never visited www with a fallback result set (always "PLC controllers"
    categories, random products) and only matches the photo afterwards —
    the page calls it with credentials: include. One homepage GET per
    session; sessions rotate on punish/exit change, so the check is cheap."""
    sess = _session()
    if getattr(_local, "site_primed", None) is sess and sess.cookies.get("cna"):
        return
    try:
        sess.get(f"{BASE}/", headers=PAGE_HEADERS, timeout=PAGE_TIMEOUT, allow_redirects=True)
    except Exception as e:
        raise AlibabaUpstreamError(f"could not open a site session: {type(e).__name__}: {e}")
    _local.site_primed = sess


# ---- mtop (reviews) --------------------------------------------------------

def _mtop_token(sess):
    tok = sess.cookies.get("_m_h5_tk") or ""
    return tok.split("_")[0]


def _mtop_once(api, data, version="1.0"):
    sess = _session()
    payload = json.dumps(data, separators=(",", ":"))
    last = None
    # First call without a token seeds _m_h5_tk (FAIL_SYS_TOKEN_EMPTY), the
    # second signs with it. Two rounds cover a token that expired mid-session.
    for _ in range(3):
        t = str(int(time.time() * 1000))
        token = _mtop_token(sess)
        sign = hashlib.md5(f"{token}&{t}&{MTOP_APP_KEY}&{payload}".encode()).hexdigest()
        url = (f"{MTOP}/{api}/{version}/?jsv=2.7.2&appKey={MTOP_APP_KEY}&t={t}&sign={sign}"
               f"&api={api}&v={version}&type=originaljson&dataType=json&data={quote(payload)}")
        try:
            resp = sess.get(url, headers=JSON_HEADERS, timeout=JSON_TIMEOUT)
        except Exception as e:
            raise AlibabaUpstreamError(f"mtop request failed: {type(e).__name__}: {e}")
        if resp.status_code in (403, 429):
            raise AlibabaBlocked(f"HTTP {resp.status_code} from mtop")
        try:
            body = resp.json()
        except Exception:
            dump_debug("nonjson_mtop", resp.text)
            raise AlibabaUpstreamError("non-JSON mtop response")
        ret = " ".join(body.get("ret") or [])
        if ret.startswith("SUCCESS"):
            return body.get("data") or {}
        last = ret
        if "TOKEN_EMPTY" in ret or "TOKEN_EXOIRED" in ret or "TOKEN_EXPIRED" in ret or "ILLEGAL_ACCESS" in ret:
            continue
        if "BIZPARAM" in ret or "PARAM" in ret:
            raise AlibabaBadRequest(ret)
        raise AlibabaUpstreamError(f"mtop {api}: {ret}")
    raise AlibabaUpstreamError(f"mtop {api}: token handshake failed ({last})")


def mtop(api, data, version="1.0"):
    """Signed mtop call (acs.h.alibaba.com); returns the `data` object."""
    return _retrying(lambda: _mtop_once(api, data, version))


# ---- the one browser surface: supplier search --------------------------------
# A real Chrome (browser.py) is primed on a plain keyword search page (mints
# the session cookies), then navigates to the gated URL. Punish -> the
# browser is retired and the next attempt launches a fresh one.
WARM_SEED_URL = f"{BASE}/trade/search?SearchText=bluetooth+speaker"


def fetch_gated_page(url, referer=None):
    """Fetch one fingerprint-gated page (supplier search) with the real
    browser; returns the HTML. Retries transport errors and punishes on a
    fresh browser; BadRequest surfaces immediately."""
    from browser import BROWSER, BrowserError

    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            if not BROWSER.primed:
                html, status = BROWSER.navigate(WARM_SEED_URL, referer="https://www.google.com/")
                if looks_punished(html):
                    dump_debug("punished_seed", html)
                    raise AlibabaBlocked("alibaba punish page on the seed search (this IP is rate-limited; "
                                         "wait a few minutes or set ALIBABA_PROXY)")
                BROWSER.mark_primed()
            html, status = BROWSER.navigate(url, referer=referer or f"{BASE}/")
        except BrowserError as e:
            last = AlibabaUpstreamError(f"browser failed: {e}")
            BROWSER.retire()
        except AlibabaUpstreamError as e:
            last = e
            BROWSER.retire()
        else:
            if status in (403, 429) or looks_punished(html):
                dump_debug("punished_gated", html)
                BROWSER.retire()
                last = AlibabaBlocked(f"alibaba punish page (status={status}) for {url}")
            elif status == 400:
                raise AlibabaBadRequest(html[:200])
            elif (status not in (None, 200)) or not html.strip():
                last = AlibabaUpstreamError(f"HTTP {status} for {url}")
            else:
                return html
        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


# ---- helpers shared by the endpoint modules --------------------------------

def build_url(path, params):
    """BASE + path + query, dropping None/"" params."""
    clean = {k: v for k, v in params.items() if v not in (None, "", [])}
    return f"{BASE}{path}?{urlencode(clean)}" if clean else f"{BASE}{path}"


_BLOB_CACHE_RE = {}


def extract_blob(html, name):
    """Parse the JSON object assigned to `window.<name> = {...};` in a page.
    Returns None when the assignment is absent or empty ({})."""
    rx = _BLOB_CACHE_RE.get(name)
    if rx is None:
        rx = re.compile(r"window\." + re.escape(name) + r"\s*=\s*(\{.*?\})\s*;?\s*</script>", re.S)
        _BLOB_CACHE_RE[name] = rx
    m = rx.search(html)
    if not m:
        return None
    raw = m.group(1)
    if raw.strip() in ("{}", ""):
        return None
    try:
        return json.loads(raw)
    except ValueError:
        # the blob may be followed by more statements before </script>
        end = _balanced_end(raw)
        if end:
            try:
                return json.loads(raw[:end])
            except ValueError:
                pass
        dump_debug(f"unparsable_{name}", html)
        raise AlibabaUpstreamError(f"could not parse window.{name}")


def _balanced_end(s):
    depth = 0
    in_str = False
    esc = False
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


if __name__ == "__main__":
    # Smoke: python alibaba/fetch.py [url]
    target = sys.argv[1] if len(sys.argv) > 1 else f"{BASE}/catalog/x_cid0?SearchText=usb+hub"
    html, final = fetch_page(target)
    print(f"bytes={len(html)} final={final} punished={looks_punished(html)}")
