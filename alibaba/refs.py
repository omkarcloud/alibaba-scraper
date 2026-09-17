"""Reference resolvers: ONE param per input that auto-detects its forms
(tripadvisor QueryOrIdField convention — never a sibling `url`/`id` pair).

  product     1601302079515
              https://www.alibaba.com/product-detail/TG117-Speaker_1601302079515.html
              //www.alibaba.com/product-detail/_1601302079515.html
  supplier    eptusbchina
              https://eptusbchina.en.alibaba.com/
              https://eptusbchina.en.alibaba.com/company_profile/feedback.html
              https://eptusbchina.m.en.alibaba.com/?productId=...
  category    518
              https://www.alibaba.com/catalog/Speakers_cid518
              https://www.alibaba.com/trade/search?categoryId=518&SearchText=...
              https://www.alibaba.com/Consumer-Electronics_p44

Every resolver returns the canonical value or raises ValueError with a
message fit for a 400 body.
"""
import re
from urllib.parse import urlparse, parse_qs

_PRODUCT_URL_RE = re.compile(r"/product-detail/[^?#]*?_(\d{6,})\.html", re.I)
_CID_RE = re.compile(r"_cid(\d+)(?:[/?#]|$)", re.I)
_P_RE = re.compile(r"/[A-Za-z0-9%._-]+_p(\d+)(?:[/?#]|$)")
_SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$", re.I)
_STORE_HOST_RE = re.compile(r"^([a-z0-9-]+)\.(?:m\.)?en\.alibaba\.com$", re.I)


def _is_url(value):
    return value.startswith(("http://", "https://", "//"))


def _parsed(value):
    return urlparse(value if not value.startswith("//") else "https:" + value)


def resolve_product_ref(value):
    """id | product-detail URL -> int product id."""
    value = (value or "").strip()
    if not value:
        raise ValueError("product is required")
    if value.isdigit():
        return int(value)
    if _is_url(value):
        u = _parsed(value)
        if not u.hostname or not u.hostname.endswith("alibaba.com"):
            raise ValueError("product must be a numeric product id or an alibaba.com product-detail link")
        m = _PRODUCT_URL_RE.search(u.path)
        if m:
            return int(m.group(1))
        raise ValueError("product link must look like https://www.alibaba.com/product-detail/<slug>_<id>.html")
    raise ValueError("product must be a numeric product id or an alibaba.com product-detail link")


def resolve_supplier_ref(value):
    """subdomain | store URL -> store subdomain (the <sub> of <sub>.en.alibaba.com).

    A numeric company id is rejected here: alibaba.com has no public
    company-id -> store lookup, so details/products need the subdomain
    (search results, product details and supplier search all carry it).
    """
    value = (value or "").strip()
    if not value:
        raise ValueError("supplier is required")
    if _is_url(value):
        u = _parsed(value)
        m = _STORE_HOST_RE.match(u.hostname or "")
        if not m:
            raise ValueError("supplier link must be a store link like https://<store>.en.alibaba.com/")
        return m.group(1).lower()
    if value.isdigit():
        raise ValueError("supplier must be the store subdomain (e.g. eptusbchina) or a store link like "
                         "https://eptusbchina.en.alibaba.com/ — numeric company ids cannot be resolved to a store")
    host = value.lower()
    m = _STORE_HOST_RE.match(host)
    if m:
        return m.group(1)
    if _SUBDOMAIN_RE.match(host) and host not in ("www", "en", "m", "sale", "fb", "acs"):
        return host
    raise ValueError("supplier must be the store subdomain (e.g. eptusbchina) or a store link like "
                     "https://eptusbchina.en.alibaba.com/")


def resolve_category_ref(value):
    """id | catalog/search/category-page URL -> int category id."""
    value = (value or "").strip()
    if not value:
        raise ValueError("category is required")
    if value.isdigit():
        return int(value)
    if _is_url(value):
        u = _parsed(value)
        if not u.hostname or not u.hostname.endswith("alibaba.com"):
            raise ValueError("category must be a numeric category id or an alibaba.com category link")
        m = _CID_RE.search(u.path)
        if m:
            return int(m.group(1))
        qs = parse_qs(u.query)
        for key in ("categoryId", "CatId", "categoryIds"):
            if qs.get(key) and qs[key][0].isdigit():
                return int(qs[key][0])
        m = _P_RE.search(u.path)
        if m:
            return int(m.group(1))
        raise ValueError("category link must carry a category id (…_cid518, ?categoryId=518 or …_p44)")
    raise ValueError("category must be a numeric category id or an alibaba.com category link")


_IMAGE_PATH_RE = re.compile(r"^/icbuimgsearch/[A-Za-z0-9._-]+$")


def resolve_image_ref(value):
    """photo URL | image_path from a previous response -> the value as-is.

    Returns an `/icbuimgsearch/...` path unchanged (the caller reuses the
    already-uploaded photo) or a public http(s) URL unchanged (the caller
    uploads it). ONE param for both forms, like the other resolvers."""
    value = (value or "").strip()
    if not value:
        raise ValueError("image is required")
    if _IMAGE_PATH_RE.match(value):
        return value
    if value.lower().startswith(("http://", "https://")):
        return value
    raise ValueError("image must be a public http(s) link to a JPEG/PNG photo, or the "
                     "`image_path` a previous response returned (e.g. /icbuimgsearch/abc123.jpg)")


def product_link(product_id):
    return f"https://www.alibaba.com/product-detail/_{product_id}.html"


def store_link(subdomain):
    return f"https://{subdomain}.en.alibaba.com/"
