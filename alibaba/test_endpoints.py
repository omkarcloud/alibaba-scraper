"""Offline tests for reference resolution, marshmallow schemas, request URL
building and route response shaping (fetch layer monkeypatched — no network).

    python -m pytest alibaba/test_endpoints.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alibaba import refs, schemas, search, product, supplier, discovery, fetch  # noqa: E402
from scraper_utils.testing import hosted_only

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load(name):
    with open(os.path.join(FX, name)) as f:
        return json.load(f)


# ---- refs ------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("1601302079515", 1601302079515),
    ("https://www.alibaba.com/product-detail/TG117-Speaker_1601302079515.html", 1601302079515),
    ("//www.alibaba.com/product-detail/_1601302079515.html?spm=x", 1601302079515),
    ("https://german.alibaba.com/product-detail/x_1601302079515.html", 1601302079515),
])
def test_product_ref(value, expected):
    assert refs.resolve_product_ref(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "https://example.com/x_123.html", "https://www.alibaba.com/trade/search?SearchText=x"])
def test_product_ref_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_product_ref(value)


@pytest.mark.parametrize("value,expected", [
    ("eptusbchina", "eptusbchina"),
    ("EPTUSBCHINA", "eptusbchina"),
    ("https://eptusbchina.en.alibaba.com/", "eptusbchina"),
    ("https://eptusbchina.en.alibaba.com/company_profile/feedback.html", "eptusbchina"),
    ("https://eptusbchina.m.en.alibaba.com/?productId=1", "eptusbchina"),
    ("eptusbchina.en.alibaba.com", "eptusbchina"),
])
def test_supplier_ref(value, expected):
    assert refs.resolve_supplier_ref(value) == expected


@pytest.mark.parametrize("value", ["", "230860282", "https://www.alibaba.com/product-detail/x_1.html", "bad name"])
def test_supplier_ref_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_supplier_ref(value)


@pytest.mark.parametrize("value,expected", [
    ("518", 518),
    ("https://www.alibaba.com/catalog/Speakers_cid518", 518),
    ("https://www.alibaba.com/catalog/Speakers-%26-Accessories_cid127726078?viewType=null", 127726078),
    ("https://www.alibaba.com/trade/search?categoryId=44&SearchText=x", 44),
    ("https://www.alibaba.com/Consumer-Electronics_p44", 44),
])
def test_category_ref(value, expected):
    assert refs.resolve_category_ref(value) == expected


# ---- schemas ---------------------------------------------------------------

def test_product_search_schema_defaults_and_renames():
    data, err = schemas.load_query(schemas.ProductSearchSchema, {"query": "  usb  hub ", "category": "https://www.alibaba.com/catalog/x_cid518"})
    assert err is None
    assert data["query"] == "usb hub" and data["category_id"] == 518
    assert data["page"] == 1 and data["sort_by"] == "best_match" and data["currency"] is None
    assert data["trade_assurance"] is None


def test_product_search_schema_flags_and_lists():
    data, err = schemas.load_query(schemas.ProductSearchSchema, {
        "query": "x", "trade_assurance": "YES", "verified_pro": "0", "supplier_certifications": "iso, bsci,ISO",
        "min_price": "1.5", "max_price": "20", "min_review_score": "4.5", "supplier_country": "cn", "currency": "eur",
        "ships_from": "EU", "sort_by": "Orders"})
    assert err is None
    assert data["trade_assurance"] is True and data["verified_pro"] is False
    assert data["supplier_certifications"] == ["ISO", "BSCI"]
    assert data["min_price"] == 1.5 and data["supplier_country"] == "CN" and data["currency"] == "EUR"
    assert data["ships_from"] == "eu" and data["sort_by"] == "orders" and data["min_review_score"] == "4.5"


@pytest.mark.parametrize("query", [
    {},                                              # missing query
    {"query": "x", "page": "0"},
    {"query": "x", "page": "101"},
    {"query": "x", "sort_by": "cheapest"},
    {"query": "x", "min_price": "10", "max_price": "1"},
    {"query": "x", "trade_assurance": "maybe"},
    {"query": "x", "currency": "dollars"},
    {"query": "x", "typo_param": "1"},              # unknown params are rejected
    {"query": "x", "min_review_score": "3"},
])
def test_product_search_schema_rejects(query):
    data, err = schemas.load_query(schemas.ProductSearchSchema, query)
    assert data is None and err["error"].startswith("Invalid parameters") and err["errors"]


def test_supplier_reviews_schema_accepts_company_id_or_store():
    data, _ = schemas.load_query(schemas.SupplierReviewsSchema, {"supplier": "230860282"})
    assert data["supplier"] == 230860282
    data, _ = schemas.load_query(schemas.SupplierReviewsSchema, {"supplier": "https://eptusbchina.en.alibaba.com/"})
    assert data["supplier"] == "eptusbchina"
    data, err = schemas.load_query(schemas.SupplierDetailsSchema, {"supplier": "230860282"})
    assert data is None and "subdomain" in err["error"]


def test_image_search_schema():
    # ONE param, both forms (house style): photo URL or a previous image_path
    data, err = schemas.load_query(schemas.ImageSearchSchema, {"image": "https://x.com/a.jpg", "page": "2"})
    assert err is None and data["page"] == 2 and data["image"] == "https://x.com/a.jpg"
    data, err = schemas.load_query(schemas.ImageSearchSchema, {"image": "/icbuimgsearch/abc123.jpg"})
    assert err is None and data["image"] == "/icbuimgsearch/abc123.jpg"
    for bad in ({"image": "ftp://x/a.jpg"}, {"page": "1"}, {"image": "/etc/passwd"},
                {"image": "https://x.com/a.jpg", "image_url": "https://x.com/b.jpg"}):
        data, err = schemas.load_query(schemas.ImageSearchSchema, bad)
        assert data is None and err["errors"]


# ---- request building (fetch monkeypatched) ---------------------------------

def _stub_page(monkeypatch, blob_name, fixture, calls):
    def fake_fetch_page(url, referer=None, currency=None, cookies=None):
        calls.append((url, currency))
        return f"<script>window.{blob_name} = {json.dumps(load(fixture))};</script>", url
    monkeypatch.setattr(search, "fetch_page", fake_fetch_page)


def test_search_products_builds_catalog_url(monkeypatch):
    calls = []
    _stub_page(monkeypatch, "__page__data_sse10._offer_list", "catalog_search_bluetooth_filtered.json", calls)
    r = search.search_products(query="bluetooth speaker", page=2, sort_by="orders", min_price=1, max_price=50,
                               min_moq=10, trade_assurance=True, verified_supplier=True, supplier_country="cn",
                               product_certifications=["CE", "ROHS"], ships_from="eu", currency="EUR")
    url, currency = calls[0]
    assert url.startswith("https://www.alibaba.com/catalog/x_cid0?")
    for part in ("SearchText=bluetooth+speaker", "page=2", "sortType=prodSold180", "pricef=1", "pricet=50", "moqf=10",
                 "ta=y", "assessmentCompany=true", "country=CN", "productAuthTag=CE%2CROHS", "overseaShipFrom=EU"):
        assert part in url, part
    assert "moqt" not in url and "verifiedPro" not in url
    assert currency == "EUR"
    assert r["currency"] == "EUR" and r["sort_by"] == "orders" and r["count"] == 12


def test_search_products_category_only(monkeypatch):
    calls = []
    _stub_page(monkeypatch, "__page__data_sse10._offer_list", "catalog_cid44_p1.json", calls)
    r = search.search_products(category_id=44, page=1)
    assert calls[0][0] == "https://www.alibaba.com/catalog/x_cid44"
    assert r["category_id"] == 44 and r["query"] is None


def test_search_products_validation():
    with pytest.raises(ValueError):
        search.search_products()
    with pytest.raises(ValueError):
        search.search_products(query="x", page=101)
    with pytest.raises(ValueError):
        search.search_products(query="x", sort_by="nope")


def test_product_details_and_missing(monkeypatch):
    def fake_fetch_page(url, referer=None, currency=None, cookies=None):
        if "x_1601302079515" in url:
            return f"<script>window.detailData = {json.dumps(load('pdp_1601302079515.json'))};</script>", url
        with open(os.path.join(FX, "pdp_not_available.html")) as f:
            return f.read(), url
    monkeypatch.setattr(product, "fetch_page", fake_fetch_page)
    p = product.product_details("https://www.alibaba.com/product-detail/x_1601302079515.html", currency="usd")
    assert p["id"] == 1601302079515 and p["currency_requested"] == "USD"
    with pytest.raises(fetch.AlibabaNotFound):
        product.product_details(1)


def test_product_reviews_learns_company_id(monkeypatch):
    calls = []

    def fake_mtop(api, data, version="1.0"):
        calls.append(dict(data))
        if "companyId" not in data:
            raise fetch.AlibabaBadRequest("FAIL_SYS_BIZPARAM_MISSED::companyId")
        return load("mtop_reviews_1601302079515_p1.json")["data"]

    monkeypatch.setattr(product, "mtop", fake_mtop)
    monkeypatch.setattr(product, "_product_page", lambda pid, currency=None: load("pdp_1601302079515.json"))
    r = product.product_reviews(1601302079515, page=1, page_size=5)
    assert calls[-1]["companyId"] == 230860282 and r["product_id"] == 1601302079515
    assert r["count"] == 5 and r["pagination"]["total_count"] == 26


def test_supplier_products_url_and_shape(monkeypatch):
    calls = []

    def fake_fetch_page(url, referer=None, currency=None, cookies=None):
        calls.append(url)
        return "<html></html>", url
    monkeypatch.setattr(supplier, "fetch_page", fake_fetch_page)
    monkeypatch.setattr(supplier, "store_modules", lambda html: load("store_productlist_modules.json"))
    r = supplier.supplier_products("https://eptusbchina.en.alibaba.com/", page=1, query="speaker", sort_by="price")
    assert calls[0] == "https://eptusbchina.en.alibaba.com/productlist.html?SearchText=speaker&sortType=price"
    assert r["supplier"]["id"] == 230860282 and r["count"] == 16
    with pytest.raises(ValueError):
        supplier.supplier_products("eptusbchina", sort_by="cheapest")


def test_supplier_reviews_by_company_id(monkeypatch):
    seen = {}

    def fake_mtop(api, data, version="1.0"):
        seen.update(data)
        return load("mtop_reviews_1601302079515_p1.json")["data"]
    monkeypatch.setattr(supplier, "mtop", fake_mtop)
    r = supplier.supplier_reviews("230860282", page=2, page_size=5)
    assert seen == {"companyId": 230860282, "currentPage": 2, "pageSize": 5}
    assert r["supplier"] == {"id": 230860282, "subdomain": None, "link": None}


def test_categories_children_accepts_link(monkeypatch):
    calls = []

    def fake_fetch_json(url, params=None, data=None):
        calls.append(params)
        return load("categories_10813_44.json") if params.get("modelId") == "10813" else load("categories_10739.json")
    monkeypatch.setattr(discovery, "fetch_json", fake_fetch_json)
    r = discovery.categories("https://www.alibaba.com/catalog/Consumer-Electronics_cid44")
    assert calls[0] == {"modelId": "10813", "categoryIds": 44} and r["parent_id"] == 44
    tree = discovery.categories()
    assert tree["count"] == 49


# ---- route shaping (bottle app, no network) ---------------------------------

def test_route_pagination_links(monkeypatch):
    os.environ["ONLY_SCRAPER"] = "alibaba"
    import importlib
    import config
    importlib.reload(config)
    import routes
    importlib.reload(routes)
    from bottle import default_app
    _stub_page(monkeypatch, "__page__data_sse10._offer_list", "catalog_search_bluetooth_filtered.json", [])
    app = default_app()
    from io import BytesIO
    env = {"REQUEST_METHOD": "GET", "PATH_INFO": "/alibaba/products/search",
           "QUERY_STRING": "query=bluetooth+speaker&page=2&currency=inr", "HTTP_X_FORWARDED_HOST": "alibaba-scraper.omkar.cloud",
           "SERVER_NAME": "localhost", "SERVER_PORT": "80", "wsgi.input": BytesIO(b""), "wsgi.errors": sys.stderr,
           "wsgi.url_scheme": "http", "wsgi.version": (1, 0), "wsgi.multithread": False, "wsgi.multiprocess": False, "wsgi.run_once": False}
    status = {}

    # bottle 0.12 calls start_response with 2 args, 0.13 always passes a
    # third (exc_info, usually None) — accept both.
    def start_response(code, headers, exc_info=None):
        status.update(status=code)

    body = b"".join(app(env, start_response))
    assert status["status"].startswith("200")
    out = json.loads(body)
    assert list(out)[:6] == ["count", "per_page", "current_page", "total_pages", "next", "previous"]
    assert out["current_page"] == 2 and out["count"] == 1214 and out["per_page"] == 48
    assert len(out["results"]) == 12
    assert out["next"] == "https://alibaba-scraper.omkar.cloud/alibaba/products/search?query=bluetooth+speaker&page=3&currency=inr"
    assert out["previous"] == "https://alibaba-scraper.omkar.cloud/alibaba/products/search?query=bluetooth+speaker&page=1&currency=inr"
    assert out["results"][0]["price"]["currency"] == "INR"
    # validation error shape (fresh environ: bottle caches the parsed query on it)
    env2 = dict(env, QUERY_STRING="query=x&page=0")
    for key in list(env2):
        if key.startswith("bottle."):
            del env2[key]
    status = {}
    body = b"".join(app(env2, start_response))
    assert status["status"].startswith("400") and json.loads(body)["errors"]["page"]


def test_image_search_flow(monkeypatch):
    calls = []
    monkeypatch.setattr(search, "_upload_image", lambda url: "/icbuimgsearch/abc123.jpg")
    monkeypatch.setattr(search, "ensure_site_cookies", lambda: None)

    def fake_fetch_json(url, params=None, data=None):
        calls.append((url, dict(params or {})))
        return load("image_search_gateway_p1.json")
    monkeypatch.setattr(search, "fetch_json", fake_fetch_json)
    r = search.search_by_image("https://example.com/photo.jpg", page=2, category_id=201148910, region="1,2,3,4")
    url, params = calls[0]
    assert url.endswith("/openservice/imageSearchViewService")
    assert params == {"pageSize": 20, "beginPage": 2, "imageType": "oss", "imageAddress": "/icbuimgsearch/abc123.jpg",
                      "categoryId": 201148910, "region": "1,2,3,4", "language": "en"}
    assert r["image_path"] == "/icbuimgsearch/abc123.jpg" and r["count"] == 8 and r["category_id"] == 201148910
    # the same param carrying a previous image_path skips the upload
    monkeypatch.setattr(search, "_upload_image", lambda url: pytest.fail("must not upload"))
    r = search.search_by_image("/icbuimgsearch/abc123.jpg", page=1)
    assert r["image_path"] == "/icbuimgsearch/abc123.jpg"
    # ... and so does the full OSS URL responses return now, in any bucket region
    for oss in ("https://icbu-picture.oss-us-west-1.aliyuncs.com/icbuimgsearch/imageBase64_ab12.jpeg",
                "https://icbu-picture-sh.oss-cn-shanghai.aliyuncs.com/icbuimgsearch/imageBase64_cd34.jpeg"):
        assert search.search_by_image(oss, page=2)["image_path"] == oss
    assert refs.is_uploaded_image("https://example.com/icbuimgsearch/x.jpg") is False
    for bad in ({"image": "https://example.com/p.jpg", "region": "1,2"}, {"image": "ftp://x/a.jpg"}, {"image": ""}):
        with pytest.raises(ValueError):
            search.search_by_image(**bad)
    data, err = schemas.load_query(schemas.ImageSearchSchema, {"image": "/icbuimgsearch/abc123.jpg", "region": "1, 2,3,4",
                                                              "category": "https://www.alibaba.com/catalog/x_cid44"})
    assert err is None and data["region"] == "1,2,3,4" and data["category_id"] == 44


def test_upload_image_posts_the_search_bar_canvas(monkeypatch):
    import base64
    import io
    import curl_cffi.requests as curl_requests
    from PIL import Image

    src = Image.new("RGBA", (1200, 600), (255, 0, 0, 0))           # transparent, wider than tall
    buf = io.BytesIO(); src.save(buf, "PNG")

    class Resp:
        status_code = 200
        headers = {"content-type": "image/png"}
        content = buf.getvalue()
    monkeypatch.setattr(curl_requests, "get", lambda *a, **k: Resp())
    posted = []

    def fake_fetch_json(url, params=None, data=None):
        posted.append((url, data))
        return {"success": True, "model": {"imagePath": "https://icbu-picture.oss-us-west-1.aliyuncs.com"
                                           "/icbuimgsearch/imageBase64_ab12.jpeg", "regions": ["0,499,0,249"]}}
    monkeypatch.setattr(search, "fetch_json", fake_fetch_json)
    assert search._upload_image("https://example.com/p.png") == \
        "https://icbu-picture.oss-us-west-1.aliyuncs.com/icbuimgsearch/imageBase64_ab12.jpeg"
    url, data = posted[0]
    assert url == "https://www.alibaba.com/search/api/imageTextSearchRegions"
    head, b64 = data["pictureBase"].split(",", 1)
    assert head == "data:image/jpeg;base64"
    sent = Image.open(io.BytesIO(base64.b64decode(b64)))
    assert sent.format == "JPEG" and sent.size == (500, 250)          # longer side 500, aspect kept
    assert sent.getpixel((10, 10))[0] > 240                          # transparency drawn on white
    # a refusal (no imagePath) is an upstream error, not a silent empty search
    monkeypatch.setattr(search, "fetch_json", lambda *a, **k: {"success": False, "msgCode": "X"})
    with pytest.raises(fetch.AlibabaUpstreamError):
        search._upload_image("https://example.com/p.png")
    # ... and so is a non-object body or a `model` that is not an object
    for body in ([], "oops", {"success": True, "model": "x"}, {"success": True, "model": {"imagePath": "/etc/passwd"}}):
        monkeypatch.setattr(search, "fetch_json", lambda *a, _b=body, **k: _b)
        with pytest.raises(fetch.AlibabaUpstreamError):
            search._upload_image("https://example.com/p.png")


def test_upload_image_applies_exif_orientation(monkeypatch):
    """The browser draws a phone photo upright (EXIF orientation applied),
    so the uploaded frame — and the regions the detector returns — must be
    the rotated one, not the raw sensor frame."""
    import base64
    import io
    import curl_cffi.requests as curl_requests
    from PIL import Image

    src = Image.new("RGB", (1000, 400), "blue")                       # stored landscape ...
    exif = Image.Exif(); exif[0x0112] = 6                             # ... tagged "rotate 90° CW"
    buf = io.BytesIO(); src.save(buf, "JPEG", exif=exif.tobytes())

    class Resp:
        status_code = 200
        headers = {"content-type": "image/jpeg"}
        content = buf.getvalue()
    monkeypatch.setattr(curl_requests, "get", lambda *a, **k: Resp())
    posted = []

    def fake_fetch_json(url, params=None, data=None):
        posted.append(data)
        return {"success": True, "model": {"imagePath": "https://icbu-picture.oss-us-west-1.aliyuncs.com"
                                           "/icbuimgsearch/imageBase64_ef56.jpeg", "regions": []}}
    monkeypatch.setattr(search, "fetch_json", fake_fetch_json)
    search._upload_image("https://example.com/phone.jpg")
    sent = Image.open(io.BytesIO(base64.b64decode(posted[0]["pictureBase"].split(",", 1)[1])))
    assert sent.size == (200, 500)                                    # portrait after the transpose


def test_image_region_must_have_an_area(monkeypatch):
    monkeypatch.setattr(search, "_upload_image", lambda url: pytest.fail("must not upload"))
    monkeypatch.setattr(search, "fetch_json", lambda *a, **k: pytest.fail("must not search"))
    for bad in ("5,5,0,9", "9,1,0,9", "0,9,7,7", "0,9,8,2"):
        with pytest.raises(ValueError):
            search.search_by_image("/icbuimgsearch/abc123.jpg", region=bad)
        _, err = schemas.load_query(schemas.ImageSearchSchema, {"image": "/icbuimgsearch/abc123.jpg", "region": bad})
        assert err and "region" in err["errors"]
    data, err = schemas.load_query(schemas.ImageSearchSchema, {"image": "/icbuimgsearch/abc123.jpg", "region": "0,498,172,500"})
    assert err is None and data["region"] == "0,498,172,500"


def test_image_regions_negative_coordinates_are_clamped():
    from alibaba import parsers
    out = parsers.parse_image_search_page({"regions": ["-1,498,172,500", "0,499,0,499"],
                                           "selectRegion": "-3,10,0,9", "offers": []}, 1)
    assert out["regions"] == ["0,498,172,500", "0,499,0,499"] and out["selected_region"] == "0,10,0,9"


# ---- exits: always a proxy, a fresh one after a punish ---------------------------

def test_sessions_always_leave_through_an_exit_and_a_punish_rotates_it(monkeypatch):
    import curl_cffi.requests as curl_requests

    class FakeSession:
        def __init__(self, impersonate=None):
            self.proxies = {}

        def close(self):
            pass

    ports = iter(range(10001, 10010))
    monkeypatch.setattr(curl_requests, "Session", FakeSession)
    monkeypatch.setattr(fetch.config, "alibaba_proxy", lambda: f"http://dc:x@gw:{next(ports)}")
    monkeypatch.setattr(fetch.config, "MAX_RETRIES", 2)
    monkeypatch.setattr(fetch.config, "RETRY_BACKOFF", 0)
    monkeypatch.setattr(fetch.config, "ALIBABA_REQUESTS_PER_EXIT", 3)
    fetch._drop_session()
    first = fetch._session()
    assert first.proxies == {"http": "http://dc:x@gw:10001", "https": "http://dc:x@gw:10001"}
    assert fetch._session() is first                                 # sticky within the budget

    seen = []

    def punished():
        seen.append(fetch._session().proxies["https"])
        raise fetch.AlibabaBlocked("alibaba punish page")
    with pytest.raises(fetch.AlibabaBlocked):
        fetch._retrying(punished)
    assert seen == ["http://dc:x@gw:10001", "http://dc:x@gw:10002"]   # the retry left on a fresh exit
    # the per-exit request budget rotates too
    fetch._drop_session()
    s = fetch._session(); fetch._session(); fetch._session()
    assert fetch._session() is not s
    fetch._drop_session()


# ---- the gated-page exit pool (fetch.fetch_gated_page) -----------------------------------

@hosted_only
def test_gated_pages_spread_over_sticky_exits_and_a_punish_rotates_that_exit(monkeypatch):
    import itertools
    import browser_client
    import config
    ports = itertools.count(20001)
    monkeypatch.setattr(config, "residential_proxy", lambda country, states=None: f"http://u:p@gw:{next(ports)}")
    monkeypatch.setattr(config, "ALIBABA_BROWSER_SLOTS", 2)
    monkeypatch.setattr(config, "BROWSER_BURST_FACTOR", 1)
    fetch._GATED_EXITS.reset()
    busy, log, answers = set(), [], []

    def fetch_any(site, candidates, **kw):
        index = next(i for i in range(len(candidates)) if i not in busy)
        log.append((candidates[index][0], [c[0] for c in candidates]))
        if answers:
            e = answers.pop(0); e.candidate = index
            raise e
        return index, {"status": 200, "headers": {}, "body": "<html>suppliers</html>", "final_url": kw.get("url")}
    monkeypatch.setattr(browser_client, "fetch_any", fetch_any)
    assert fetch.fetch_gated_page("https://www.alibaba.com/trade/search?tab=supplier&SearchText=a") == "<html>suppliers</html>"
    busy.add(0)
    fetch.fetch_gated_page("https://www.alibaba.com/trade/search?tab=supplier&SearchText=b")
    busy.clear()
    fetch.fetch_gated_page("https://www.alibaba.com/trade/search?tab=supplier&SearchText=c")
    assert [p for p, _ in log] == ["http://u:p@gw:20001", "http://u:p@gw:20002", "http://u:p@gw:20001"]
    assert log[-1][1] == ["http://u:p@gw:20001", "http://u:p@gw:20002"]
    # punished once: the exit the box used is rotated and the call retried on the pool
    answers.append(browser_client.BoxRefused("alibaba/fetch: 502 recipe punished"))
    assert fetch.fetch_gated_page("https://www.alibaba.com/trade/search?tab=supplier&SearchText=d") == "<html>suppliers</html>"
    assert fetch._GATED_EXITS.current() == ["http://u:p@gw:20003", "http://u:p@gw:20002"]
    assert [p for p, _ in log][-2:] == ["http://u:p@gw:20001", "http://u:p@gw:20003"]
    # punished twice in a row: blocked
    answers.extend([browser_client.BoxRefused("p1"), browser_client.BoxRefused("p2")])
    with pytest.raises(fetch.AlibabaBlocked):
        fetch.fetch_gated_page("https://www.alibaba.com/trade/search?tab=supplier&SearchText=e")
    monkeypatch.setattr(config, "BROWSER_BURST_FACTOR", 4)
    fetch.fetch_gated_page("https://www.alibaba.com/trade/search?tab=supplier&SearchText=f")
    assert len(log[-1][1]) == 8                                # share x the default factor
    fetch._GATED_EXITS.reset()
