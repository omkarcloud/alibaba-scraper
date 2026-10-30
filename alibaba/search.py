"""Product search (keyword / category / image) and supplier search.

Keyword + category search ride the /catalog/x_cid<id|0> surface, the one
alibaba.com surface that accepts SearchText AND every filter without the
baxia punish (alibaba/fetch.py docstring). Supplier search and image search
are fingerprint-gated and go through the browser pool.

    python alibaba/search.py "bluetooth speaker" [page]
    python alibaba/search.py --category 518
    python alibaba/search.py --suppliers "bluetooth speaker"
    python alibaba/search.py --image https://…/photo.jpg
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alibaba import parsers  # noqa: E402
from alibaba.fetch import (  # noqa: E402
    BASE, OPEN_S, AlibabaNotFound, AlibabaUpstreamError, build_url, ensure_site_cookies,
    extract_blob, fetch_gated_page, fetch_json, fetch_page,
)
from alibaba.refs import is_uploaded_image, resolve_image_ref  # noqa: E402

MAX_PAGE = parsers.SEARCH_MAX_PAGES

# public sort key -> site sortType
SORT_OPTIONS = {
    "best_match": "",
    "orders": "prodSold180",        # "Sort by sales volume"
    "response_rate": "RESRAT",
}
# public ships_from region -> overseaShipFrom
SHIPS_FROM_OPTIONS = {"eu": "EU", "us": "US", "gb": "GB", "de": "DE", "any": ""}
REVIEW_SCORE_OPTIONS = ("4", "4.5", "5")


def _catalog_path(category_id):
    return f"/catalog/x_cid{int(category_id) if category_id else 0}"


def search_products(query=None, category_id=None, page=1, sort_by="best_match",
                    min_price=None, max_price=None, min_moq=None, max_moq=None,
                    min_review_score=None, supplier_country=None,
                    trade_assurance=None, verified_supplier=None, verified_pro=None,
                    alibaba_guaranteed=None, free_sample=None, ships_from=None,
                    delivery_days=None, supplier_certifications=None,
                    product_certifications=None, currency=None):
    """Keyword and/or category product search with filters. Returns the
    parsers.parse_search_page shape (48 per page, 100 pages max)."""
    if not query and not category_id:
        raise ValueError("query or category_id is required")
    page = int(page or 1)
    if not 1 <= page <= MAX_PAGE:
        raise ValueError(f"page must be 1-{MAX_PAGE}")
    if sort_by not in SORT_OPTIONS:
        raise ValueError(f"sort_by must be one of: {', '.join(SORT_OPTIONS)}")
    if min_review_score is not None and str(min_review_score) not in REVIEW_SCORE_OPTIONS:
        raise ValueError("min_review_score must be one of: 4, 4.5, 5")
    if ships_from is not None and str(ships_from).lower() not in SHIPS_FROM_OPTIONS:
        raise ValueError(f"ships_from must be one of: {', '.join(SHIPS_FROM_OPTIONS)}")
    params = {
        "SearchText": query or None,
        "page": page if page > 1 else None,
        "sortType": SORT_OPTIONS[sort_by] or None,
        "pricef": _num(min_price),
        "pricet": _num(max_price),
        "moqf": _num(min_moq),
        "moqt": _num(max_moq),
        "reviewScore": str(min_review_score) if min_review_score is not None else None,
        "country": (supplier_country or "").upper() or None,
        "ta": "y" if trade_assurance else None,
        "assessmentCompany": "true" if verified_supplier else None,
        "verifiedPro": "1" if verified_pro else None,
        "halfTrust": "true" if alibaba_guaranteed else None,
        "freeSample": "1" if free_sample else None,
        "overseaShipFrom": SHIPS_FROM_OPTIONS.get(str(ships_from).lower()) if ships_from else None,
        "deliveryDay": _num(delivery_days),
        "companyAuthTag": ",".join(supplier_certifications) if supplier_certifications else None,
        "productAuthTag": ",".join(product_certifications) if product_certifications else None,
    }
    url = build_url(_catalog_path(category_id), params)
    html, _final = fetch_page(url, referer=f"{BASE}/", currency=currency)
    blob = extract_blob(html, "__page__data_sse10._offer_list")
    if blob is None and "__page__data_sse10" not in html:
        raise AlibabaUpstreamError("search page rendered without the offer list blob")
    result = parsers.parse_search_page(blob, page, currency)
    if category_id:
        result["category_id"] = int(category_id)
    result["query"] = query
    result["sort_by"] = sort_by
    result["currency"] = (currency or "").upper() or None
    if page > 1 and not result["results"] and result["pagination"]["total_pages"] < page:
        raise AlibabaNotFound(f"page {page} is past the last page ({result['pagination']['total_pages']})")
    return result


def _num(value):
    if value in (None, ""):
        return None
    return int(value) if float(value).is_integer() else float(value)


# ---- supplier search (gated: browser pool) --------------------------------

def search_suppliers(query, page=1, supplier_country=None, verified_supplier=None,
                     verified_pro=None, trade_assurance=None, supplier_certifications=None):
    """Supplier (company) search: 20 companies per page with years on
    Alibaba, verification badges, response time, staff, transactions,
    rating and a featured product; filter by country, verified / verified
    pro / trade assurance and company certifications (ISO, BSCI, ...)."""
    if not query:
        raise ValueError("query is required")
    page = int(page or 1)
    if not 1 <= page <= MAX_PAGE:
        raise ValueError(f"page must be 1-{MAX_PAGE}")
    params = {
        "SearchText": query,
        "tab": "supplier",
        "page": page if page > 1 else None,
        "country": (supplier_country or "").upper() or None,
        "assessmentCompany": "true" if verified_supplier else None,
        "verifiedPro": "1" if verified_pro else None,
        "ta": "y" if trade_assurance else None,
        "companyAuthTag": ",".join(supplier_certifications) if supplier_certifications else None,
    }
    url = build_url("/trade/search", params)
    html = fetch_gated_page(url, referer=f"{BASE}/")
    blob = extract_blob(html, "_PAGE_DATA_")
    if blob is None:
        raise AlibabaUpstreamError("supplier search page rendered without _PAGE_DATA_")
    result = parsers.parse_supplier_search_page(blob, page)
    result["query"] = query
    if page > 1 and not result["results"] and result["pagination"]["total_pages"] < page:
        raise AlibabaNotFound(f"page {page} is past the last page ({result['pagination']['total_pages']})")
    return result


# ---- image search (site upload + open-s result list) -----------------------

# The search bar's own upload since ~2026-10-27 (s.alicdn.com
# pc-home-2022/js/fy25headersearchproduct.js): the photo is drawn on a canvas
# whose longer side is 500 px, exported as a JPEG q0.8 data URL and POSTed as
# `pictureBase`; the answer is {"success": true, "model": {"imagePath":
# "https://icbu-picture.oss-us-west-1.aliyuncs.com/icbuimgsearch/imageBase64_<id>.jpeg",
# "regions": [...]}}. A plain form POST works and needs no cookies
# (validated 2026-10-30). The bucket follows the uploader's IP (a US exit
# gets icbu-picture.oss-us-west-1, an Indian one icbu-picture-sh.oss-cn-
# shanghai), and the result list only finds a non-US upload by its full URL,
# so `image_path` is the full URL. The old route — a signed OSS POST policy
# from open-s ossUploadSecretKeyDataService — answers {"enable": false} on
# every exit since then.
UPLOAD_URL = f"{BASE}/search/api/imageTextSearchRegions"
UPLOAD_SIDE = 500
IMAGE_MAX_BYTES = 8 * 1024 * 1024
IMAGE_TIMEOUT = 30


def _upload_image(image_url):
    """Download the caller's image and upload it the way the site's search
    bar does (see UPLOAD_URL); returns the full OSS URL the result list takes
    as imageAddress."""
    import base64
    import io

    from PIL import Image

    from alibaba.fetch import IMPERSONATE

    from curl_cffi import requests as curl_requests
    # Ask for JPEG/PNG explicitly: CDNs that content-negotiate (alicdn) answer
    # `image/*` with AVIF, which Pillow cannot decode (validated 2026-09-14).
    try:
        resp = curl_requests.get(image_url, impersonate=IMPERSONATE, timeout=IMAGE_TIMEOUT,
                                 headers={"accept": "image/jpeg,image/png;q=0.9,*/*;q=0.5"},
                                 allow_redirects=True)
    except Exception as e:
        raise ValueError(f"could not download image_url: {type(e).__name__}")
    ctype = (resp.headers.get("content-type") or "").lower()
    body = resp.content or b""
    if body[4:12] in (b"ftypavif", b"ftypavis", b"ftypheic", b"ftypmif1"):
        raise ValueError("image_url must point to a JPEG or PNG (the server only offers AVIF/HEIC)")
    if resp.status_code != 200 or len(body) < 100 or (ctype and not ctype.startswith("image/") and not body[:4] in (b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"\x89PNG", b"RIFF", b"GIF8")):
        raise ValueError("image_url must be a publicly downloadable JPEG/PNG/WEBP image "
                         f"(got HTTP {resp.status_code}, {len(body)} bytes, {ctype or 'no content-type'})")
    if len(body) > IMAGE_MAX_BYTES:
        raise ValueError("image is larger than 8 MB")
    try:
        im = Image.open(io.BytesIO(body))
        im.load()
    except Exception:
        raise ValueError("image_url must be a JPEG/PNG/WEBP image (it could not be decoded)")
    # same canvas as the site: white background (transparent PNGs), longer side 500 px
    canvas = Image.new("RGB", im.size, "white")
    im = im.convert("RGBA")
    canvas.paste(im, mask=im.split()[-1])
    canvas.thumbnail((UPLOAD_SIDE, UPLOAD_SIDE))
    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=80)
    data_url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    payload = fetch_json(UPLOAD_URL, data={"pictureBase": data_url})
    model = payload.get("model") if isinstance(payload, dict) else None
    image_path = (model or {}).get("imagePath") or ""
    if not payload.get("success") or not is_uploaded_image(image_path):
        raise AlibabaUpstreamError(f"image upload rejected: {str(payload)[:200]}")
    return image_path


IMAGE_PAGE_SIZE = 20
IMAGE_MAX_PAGE = 50
_REGION_RE = re.compile(r"\d+,\d+,\d+,\d+")


def search_by_image(image, page=1, category_id=None, region=None):
    """Reverse image search over plain curl_cffi: upload the image the way
    the site's search bar does (UPLOAD_URL, since 2026-10-30), then page the
    matches through the open-s imageSearchViewService gateway — the same JSON
    call the result page's list makes (20 offers/page, category facets,
    detected crop regions; no browser).

    ONE param for the image (house style — never a url/id pair): `image` is
    either a public http(s) photo link, which gets uploaded, or the
    `image_path` a previous response returned (the uploaded photo's OSS URL;
    the older `/icbuimgsearch/...` path form too), which skips the upload
    when paging or re-cropping the same photo."""
    page = int(page or 1)
    if not 1 <= page <= IMAGE_MAX_PAGE:
        raise ValueError(f"page must be 1-{IMAGE_MAX_PAGE}")
    if region is not None and not _REGION_RE.fullmatch(str(region)):
        raise ValueError("region must be 'x1,x2,y1,y2' pixel coordinates of the uploaded image "
                         "(the response's `regions` lists the detected ones)")
    image_path = resolve_image_ref(str(image or ""))
    if not is_uploaded_image(image_path):
        image_path = _upload_image(image_path)
    params = {
        "pageSize": IMAGE_PAGE_SIZE, "beginPage": page, "imageType": "oss",
        "imageAddress": image_path, "categoryId": int(category_id) if category_id else "",
        "region": region or "", "language": "en",
    }
    ensure_site_cookies()   # cookie-less calls get a fallback result set (see fetch.py)
    payload = fetch_json(f"{OPEN_S}/imageSearchViewService", params=params)
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise AlibabaUpstreamError("image search gateway answered without data")
    result = parsers.parse_image_search_page(data, page)
    result["image_path"] = image_path
    result["category_id"] = int(category_id) if category_id else None
    result["region"] = region or None
    if page > 1 and not result["results"]:
        raise AlibabaNotFound(f"page {page} is past the last page")
    return result


if __name__ == "__main__":
    import json
    args = sys.argv[1:]
    if args and args[0] == "--category":
        out = search_products(category_id=int(args[1]), page=int(args[2]) if len(args) > 2 else 1)
    elif args and args[0] == "--suppliers":
        out = search_suppliers(args[1], page=int(args[2]) if len(args) > 2 else 1)
    elif args and args[0] == "--image":
        out = search_by_image(args[1])
    else:
        out = search_products(query=args[0] if args else "bluetooth speaker",
                              page=int(args[1]) if len(args) > 1 else 1)
    print(json.dumps({k: v for k, v in out.items() if k != "results"}, ensure_ascii=False, indent=1)[:2000])
    print(json.dumps(out["results"][:2], ensure_ascii=False, indent=1))
