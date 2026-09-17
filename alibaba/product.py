"""Product details and product reviews.

    python alibaba/product.py 1601302079515
    python alibaba/product.py https://www.alibaba.com/product-detail/x_1601302079515.html --reviews 2
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alibaba import parsers  # noqa: E402
from alibaba.fetch import (  # noqa: E402
    BASE, AlibabaBadRequest, AlibabaNotFound, AlibabaUpstreamError, extract_blob,
    fetch_page, mtop,
)
from alibaba.refs import resolve_product_ref  # noqa: E402

REVIEW_API = "mtop.alibaba.icbu.review.media.review"
REVIEWS_PAGE_SIZE = 10
REVIEWS_MAX_PAGE_SIZE = 50


def _product_page(product_id, currency=None):
    url = f"{BASE}/product-detail/x_{product_id}.html"
    html, _final = fetch_page(url, referer=f"{BASE}/", currency=currency)
    blob = extract_blob(html, "detailData")
    if parsers.product_page_is_missing(html, blob):
        raise AlibabaNotFound(f"product {product_id} is not available")
    if blob is None:
        raise AlibabaUpstreamError("product page rendered without window.detailData")
    return blob


def product_details(product, currency=None):
    """Full product page. `product` = numeric id or product-detail link."""
    product_id = resolve_product_ref(str(product))
    blob = _product_page(product_id, currency)
    result = parsers.parse_product_page(blob, currency)
    result["currency_requested"] = (currency or "").upper() or None
    return result


def product_reviews(product, page=1, page_size=REVIEWS_PAGE_SIZE, company_id=None):
    """Reviews of one product (mtop review API; 10 per page by default).
    The API keys on productId + companyId; when the caller has no company id
    the product page is fetched once to learn it."""
    product_id = resolve_product_ref(str(product))
    page = int(page or 1)
    page_size = int(page_size or REVIEWS_PAGE_SIZE)
    if page < 1:
        raise ValueError("page must be >= 1")
    if not 1 <= page_size <= REVIEWS_MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be 1-{REVIEWS_MAX_PAGE_SIZE}")
    data = {"productId": product_id, "currentPage": page, "pageSize": page_size}
    if company_id:
        data["companyId"] = int(company_id)
    try:
        payload = mtop(REVIEW_API, data)
    except AlibabaBadRequest:
        if company_id:
            raise
        blob = _product_page(product_id)
        seller_id = parsers._dig(blob, "globalData", "seller", "companyId")
        if not seller_id:
            raise AlibabaNotFound(f"product {product_id} has no seller")
        data["companyId"] = int(seller_id)
        payload = mtop(REVIEW_API, data)
    result = parsers.parse_reviews(payload, page, page_size)
    result["product_id"] = product_id
    if page > 1 and not result["results"] and result["pagination"]["total_pages"] < page:
        raise AlibabaNotFound(f"page {page} is past the last page ({result['pagination']['total_pages']})")
    return result


if __name__ == "__main__":
    import json
    args = sys.argv[1:] or ["1601302079515"]
    if "--reviews" in args:
        i = args.index("--reviews")
        out = product_reviews(args[0], page=int(args[i + 1]) if len(args) > i + 1 else 1)
    else:
        out = product_details(args[0], currency=args[1] if len(args) > 1 else None)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:6000])
