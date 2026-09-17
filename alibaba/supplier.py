"""Supplier (store) details, product list and reviews.

Store pages live on <subdomain>.en.alibaba.com and embed their data as
URL-encoded JSON in `module-data` attributes (one per shop module); all of
them render over plain curl_cffi. company_profile.html and contactinfo.html
are punished every time and are not used — the home page's shopSign +
companyOverview modules carry the same company facts.

    python alibaba/supplier.py eptusbchina
    python alibaba/supplier.py https://eptusbchina.en.alibaba.com/ --products 2 [query]
    python alibaba/supplier.py eptusbchina --reviews 1
"""
import json
import os
import re
import sys
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alibaba import parsers  # noqa: E402
from alibaba.fetch import (  # noqa: E402
    AlibabaNotFound, AlibabaUpstreamError, build_url, fetch_page, mtop,
)
from alibaba.refs import resolve_supplier_ref  # noqa: E402

REVIEW_API = "mtop.alibaba.icbu.review.media.review"
REVIEWS_PAGE_SIZE = 10
REVIEWS_MAX_PAGE_SIZE = 50
PRODUCTS_MAX_PAGE = 500

# public sort key -> store sortType
PRODUCT_SORT_OPTIONS = {
    "newest": "modified-desc",
    "price": "price",
    "orders": "order",
    "relevance": "relevance",
    "supplier_selected": "user",
}

_MODULE_RE = re.compile(r"<([a-z]+)([^>]*?)module-data='([^']*)'([^>]*)>")
_NAME_RE = re.compile(r'module-name="([^"]*)"')


def store_url(subdomain, path=""):
    return f"https://{subdomain}.en.alibaba.com/{path.lstrip('/')}"


def store_modules(html):
    """All `module-data` blobs of a store page -> [{module_name, gdc, mds}]."""
    out = []
    for m in _MODULE_RE.finditer(html):
        attrs = m.group(2) + m.group(4)
        name = _NAME_RE.search(attrs)
        try:
            obj = json.loads(unquote(m.group(3)))
        except ValueError:
            continue
        out.append({"module_name": name.group(1) if name else None,
                    "gdc": obj.get("gdc"), "mds": obj.get("mds")})
    return out


def _store_page(subdomain, path="", currency=None):
    try:
        html, _final = fetch_page(store_url(subdomain, path), referer=store_url(subdomain), currency=currency)
    except AlibabaNotFound:
        # a non-existent store subdomain answers HTTP 200 with an empty body
        raise AlibabaNotFound(f"store {subdomain} does not exist")
    modules = store_modules(html)
    if not modules:
        raise AlibabaNotFound(f"store {subdomain} does not exist")
    return modules


def _company_id(modules):
    gdc = parsers._module_gdc(modules)
    return parsers._clean_id(gdc.get("companyId")) if gdc else None


def _review_summary(company_id):
    try:
        data = mtop(REVIEW_API, {"companyId": int(company_id), "currentPage": 1, "pageSize": 1})
    except AlibabaUpstreamError:
        return None
    return parsers._count(parsers._dig(data, "target", "totalReviewCount"))


def supplier_details(supplier):
    """Company profile assembled from the store home page (shopSign +
    companyOverview), the feedback page (performance stats) and the review
    API (review count). `supplier` = store subdomain or store link."""
    sub = resolve_supplier_ref(str(supplier))
    home = _store_page(sub)
    result = parsers.parse_store_home(home, sub)
    if not result:
        raise AlibabaUpstreamError("store home rendered without shop modules")
    perf = None
    try:
        perf = parsers.parse_store_performance(_store_page(sub, "company_profile/feedback.html"))
    except (AlibabaNotFound, AlibabaUpstreamError):
        perf = None
    result["performance"] = perf
    review_count = _review_summary(result["id"]) if result.get("id") else None
    result["rating"] = {"review_count": review_count}
    return result


def supplier_products(supplier, page=1, query=None, sort_by="newest", currency=None):
    """The store's product list (16 per page), optionally filtered by an
    in-store keyword and sorted."""
    sub = resolve_supplier_ref(str(supplier))
    page = int(page or 1)
    if not 1 <= page <= PRODUCTS_MAX_PAGE:
        raise ValueError(f"page must be 1-{PRODUCTS_MAX_PAGE}")
    if sort_by not in PRODUCT_SORT_OPTIONS:
        raise ValueError(f"sort_by must be one of: {', '.join(PRODUCT_SORT_OPTIONS)}")
    path = f"productlist-{page}.html" if page > 1 else "productlist.html"
    params = {"SearchText": query or None,
              "sortType": PRODUCT_SORT_OPTIONS[sort_by] if sort_by != "newest" else None}
    clean = {k: v for k, v in params.items() if v}
    url = store_url(sub, path) + ("?" + "&".join(f"{k}={_q(v)}" for k, v in clean.items()) if clean else "")
    html, _final = fetch_page(url, referer=store_url(sub), currency=currency)
    modules = store_modules(html)
    if not modules:
        raise AlibabaNotFound(f"store {sub} does not exist")
    result = parsers.parse_store_products(modules, page, sub)
    result["supplier"] = {"id": _company_id(modules), "subdomain": sub, "link": store_url(sub)}
    result["query"] = query
    result["sort_by"] = sort_by
    if page > 1 and result["pagination"]["page"] != page:
        # the store clamps past-the-end pages back to page 1
        raise AlibabaNotFound(f"page {page} is past the last page ({result['pagination']['total_pages']})")
    return result


def _q(value):
    from urllib.parse import quote_plus
    return quote_plus(str(value))


def supplier_reviews(supplier, page=1, page_size=REVIEWS_PAGE_SIZE):
    """Store-level reviews (every product of the company). `supplier` =
    subdomain, store link, or the numeric company id."""
    page = int(page or 1)
    page_size = int(page_size or REVIEWS_PAGE_SIZE)
    if page < 1:
        raise ValueError("page must be >= 1")
    if not 1 <= page_size <= REVIEWS_MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be 1-{REVIEWS_MAX_PAGE_SIZE}")
    value = str(supplier).strip()
    if value.isdigit():
        company_id, sub = int(value), None
    else:
        sub = resolve_supplier_ref(value)
        company_id = _company_id(_store_page(sub))
        if not company_id:
            raise AlibabaUpstreamError("store home rendered without a company id")
    data = mtop(REVIEW_API, {"companyId": company_id, "currentPage": page, "pageSize": page_size})
    result = parsers.parse_reviews(data, page, page_size)
    result["supplier"] = {"id": company_id, "subdomain": sub, "link": store_url(sub) if sub else None}
    if page > 1 and not result["results"] and result["pagination"]["total_pages"] < page:
        raise AlibabaNotFound(f"page {page} is past the last page ({result['pagination']['total_pages']})")
    return result


if __name__ == "__main__":
    args = sys.argv[1:] or ["eptusbchina"]
    if "--products" in args:
        i = args.index("--products")
        out = supplier_products(args[0], page=int(args[i + 1]) if len(args) > i + 1 else 1,
                                query=args[i + 2] if len(args) > i + 2 else None)
    elif "--reviews" in args:
        i = args.index("--reviews")
        out = supplier_reviews(args[0], page=int(args[i + 1]) if len(args) > i + 1 else 1)
    else:
        out = supplier_details(args[0])
    print(json.dumps(out, ensure_ascii=False, indent=1)[:6000])
