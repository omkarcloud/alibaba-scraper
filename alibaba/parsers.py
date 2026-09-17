"""Payload -> stable dict normalization for every alibaba.com surface.

Rules (house style): snake_case, `link` not `url`, booleans as questions,
identity first then content then ratings then nested objects then metadata,
numbers as numbers, prices as amount + currency, null for missing, never
crash on a partial payload.

Intentionally skipped raw fields (and why):
  search offers   adInfo/adActionInfo/impsEurl/clickEurl/eurl/tmlid/trackInfo/
                  chatToken/contactSupplier/wapChatNow (ad + tracking + chat
                  tokens), multiTemplate/aiMultiTemplate (ad rendering),
                  koreaAgeRestricted/lyb/customGroup/showAddToCart/showCrown
                  (presentation flags), productList (an ad's extra products —
                  they duplicate organic cards), pcLoopSellingPoints (same as
                  loopSellingPoints), supplierService (dup of
                  supplierServiceScore), moqV2 (dup of moq)
  search page     bts (A/B buckets), layoutI18nData/pageCommonData (UI strings),
                  switchData.viewAsVO (grid/list toggle), snData hrefs (built
                  from our own params instead)
  supplier cards  adInfo/trackInfo/chatToken/contactSupplier/clickEurl/impsEurl/
                  tmlid/type/galleryPerLine/hideTopBoothModel (ads + layout),
                  memberTag (opaque ids), iconList (icon images only)
  product page    globalData.i18n/abtest/risk/buyer/extend (UI strings, buckets,
                  tokens), nodeMap render configs, productEncryptId/*EncryptId/
                  chatToken (opaque tokens), globalSeoUrl (18 language mirrors
                  of the same page), recommendation modules, coupon/promotion
                  atmosphere modules, module_shipping html styling (text kept)
  reviews         trackInfo, productInfo.app/msite URLs (pc link kept),
                  repeatCnt/hasRate/valid (internal flags), userCountryFlag
  store modules   gdc/mds template + design config, i18n, menus/esiteUrls
                  (links rebuilt from the subdomain), buckets/phantBucketName
  suggestions     trackInfo, suggestKeywordHtml (plain keyword kept)
  categories      imageUrl action/searchUrl variants (one link kept), dotName
"""
import html as _html
import math
import re
from datetime import datetime, timezone

BASE = "https://www.alibaba.com"

SEARCH_PAGE_SIZE = 48
SEARCH_MAX_PAGES = 100
SUPPLIER_PAGE_SIZE = 20
STORE_PAGE_SIZE = 16

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NUM_RE = re.compile(r"\d[\d.,]*")
_INT_RE = re.compile(r"\d+")

# Currency symbol -> ISO code for price strings ("US $1.20", "€2.61-3.38",
# "₹2,976.80-3,307.34"). Ambiguous symbols (¥, kr) are resolved by the
# requested currency when the caller passed one.
_SYMBOLS = [
    ("US $", "USD"), ("HK$", "HKD"), ("NT$", "TWD"), ("S$", "SGD"), ("A$", "AUD"),
    ("C$", "CAD"), ("R$", "BRL"), ("MX$", "MXN"), ("NZ$", "NZD"), ("CHF", "CHF"),
    ("₹", "INR"), ("€", "EUR"), ("£", "GBP"), ("₩", "KRW"), ("₽", "RUB"), ("₺", "TRY"),
    ("zł", "PLN"), ("฿", "THB"), ("₫", "VND"), ("Rp", "IDR"), ("₱", "PHP"), ("RM", "MYR"),
    ("د.إ", "AED"), ("SR", "SAR"), ("₪", "ILS"), ("Kč", "CZK"), ("Ft", "HUF"),
    ("AED", "AED"), ("$", "USD"),
]


# ---- tiny helpers ----------------------------------------------------------

def _dig(obj, *path, default=None):
    cur = obj
    for key in path:
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list) and isinstance(key, int) and -len(cur) <= key < len(cur):
            cur = cur[key]
        else:
            return default
        if cur is None:
            return default
    return cur


def _text(value):
    """Strip tags/entities/whitespace; None when empty."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = _html.unescape(_TAG_RE.sub(" ", value))
    value = _WS_RE.sub(" ", value).strip()
    return value or None


def _link(value):
    """Protocol-relative / relative alibaba links -> absolute https."""
    value = _text(value)
    if not value:
        return None
    if value.startswith("//"):
        return "https:" + value
    if value.startswith("/"):
        return BASE + value
    if value.startswith("http://"):
        return "https://" + value[len("http://"):]
    return value


def _image(value):
    """Image URL without the size suffix (…jpg_300x300.jpg -> …jpg)."""
    value = _link(value)
    if not value:
        return None
    # …/H6c4d.jpg_300x300.jpg -> …/H6c4d.jpg ; …/x.png_120x120.png -> …/x.png
    return re.sub(r"_\d+x\d+(?:q\d+)?\.(?:jpe?g|png|webp|gif)$", "", value, flags=re.I)


def _int(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    m = _INT_RE.findall(str(value).replace(",", "").replace(".", ""))
    if not m:
        return None
    try:
        return int("".join(m)) if len(m) == 1 else int(m[0])
    except ValueError:
        return None


def _count(value):
    """Integer from a count-ish string ("1.000 pieces", "13062 sold",
    "5,100+ m²", "100+ staff"). Separators inside the number are thousands."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    m = _NUM_RE.search(str(value))
    if not m:
        return None
    digits = re.sub(r"[.,]", "", m.group(0))
    return int(digits) if digits else None


def _float(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("%", "")
    m = _NUM_RE.search(s)
    if not m:
        return None
    return _parse_number(m.group(0))


def _parse_number(token):
    """'2,976.80' -> 2976.8, '1.000,50' -> 1000.5, '0.7933' -> 0.7933."""
    t = token.strip(".,")
    if not t:
        return None
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):     # 1.000,50
            t = t.replace(".", "").replace(",", ".")
        else:                               # 2,976.80
            t = t.replace(",", "")
    elif "," in t:
        parts = t.split(",")
        if all(len(p) == 3 for p in parts[1:]):
            t = t.replace(",", "")          # 1,000 / 2,976
        else:
            t = t.replace(",", ".")         # 2,5
    elif t.count(".") > 1:
        t = t.replace(".", "")              # 1.000.000
    try:
        return float(t)
    except ValueError:
        return None


def _bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "1", "y", "yes"):
            return True
        if low in ("false", "0", "n", "no", ""):
            return False
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _percent(value):
    """'92.6%' -> 92.6 ; 0.17 (fraction) stays a fraction caller-side."""
    return _float(value)


def _currency_from_symbol(text, fallback=None):
    if not text:
        return fallback
    for sym, code in _SYMBOLS:
        if sym in text:
            if sym == "$" and fallback and fallback != "USD" and fallback.endswith("D"):
                return fallback   # AUD/CAD/NZD/SGD… render as a bare "$"
            return code
    if "¥" in text or "￥" in text:
        return fallback if fallback in ("JPY", "CNY") else "JPY"
    if "kr" in text.lower():
        return fallback if fallback in ("SEK", "NOK", "DKK") else "SEK"
    return fallback


def parse_price(text, currency=None):
    """'€2.61-3.38' / '$6.0~7.0' / 'US $1.20' / '₹2,976.80-3,307.34' ->
    {"min", "max", "currency", "formatted"}; None when there is no number."""
    text = _text(text)
    if not text:
        return None
    nums = [n for n in (_parse_number(t) for t in _NUM_RE.findall(text)) if n is not None]
    if not nums:
        return None
    return {
        "min": nums[0],
        "max": nums[-1] if len(nums) > 1 else nums[0],
        "currency": _currency_from_symbol(text, currency),
        "formatted": text,
    }


def parse_moq(text):
    """'Min. order: 1.000 pieces' -> {"quantity": 1000, "unit": "pieces"}."""
    text = _text(text)
    if not text:
        return None
    tail = text.split(":")[-1] if ":" in text else text
    m = re.search(r"(\d[\d.,]*)\s*([^\d]*)$", tail.strip())
    if not m:
        return None
    unit = _WS_RE.sub(" ", m.group(2)).strip(" .") or None
    return {"quantity": _count(m.group(1)), "unit": unit}


def _years(text):
    """'16 yrs' / '13 yrs' / 13 -> 16."""
    return _count(text)


def _iso_date(value):
    """'2026/07/01' | 'July 1, 2026' | '08-03-2026' (dd-mm-yyyy) -> '2026-07-01'."""
    value = _text(value)
    if not value:
        return None
    # replyTime is mm-dd-yyyy ("08-03-2026" replied to a 2026/07/01 review)
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m-%d-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value


def _pagination(page, per_page, total_count, max_pages=None):
    total_pages = math.ceil(total_count / per_page) if total_count else 0
    if max_pages:
        total_pages = min(total_pages, max_pages)
    return {
        "page": page,
        "items_per_page": per_page,
        "total_pages": total_pages,
        "total_count": total_count,
    }


def _clean_id(value):
    """Integer id; keeps the sign of placeholder ids like -1 / -2."""
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return _int(s)


# ---- product search (catalog / trade search offers) ------------------------

def _offer_card(o, currency=None):
    if not isinstance(o, dict):
        return None
    pid = _clean_id(o.get("productId") or o.get("id"))
    if not pid:
        return None
    # Two card generations coexist on the same page: the classic one (price,
    # moq, soldOrder, loopSellingPoints…) and the "V2" one (priceV2, moqV2,
    # marketingPowerCommon, fulfillmentInfo, enPureTitle…).
    price = parse_price(o.get("price") or o.get("priceV2"), currency)
    promo = parse_price(o.get("promotionPrice") or o.get("promotionPriceV2"), currency)
    mpc = o.get("marketingPowerCommon") if isinstance(o.get("marketingPowerCommon"), dict) else {}
    sold = _count(o.get("soldOrder"))
    if sold is None and mpc.get("type") == "soldQuantity":
        sold = _count(mpc.get("count") or mpc.get("text"))
    badges = []
    is_guaranteed = False
    for b in o.get("badges") or []:
        if not isinstance(b, dict):
            continue
        if b.get("loopType") == "ag":
            is_guaranteed = True
        label = _text(b.get("text")) or b.get("loopType")
        if label:
            badges.append(label)
    certs = []
    for c in o.get("certifications") or []:
        for icon in (c.get("prefixIcons") or []) if isinstance(c, dict) else []:
            name = _text(icon.get("name"))
            if name and name not in certs:
                certs.append(name)
    for c in o.get("productCertificates") or []:      # image-search gateway cards
        name = _text(c.get("name") if isinstance(c, dict) else c)
        if name and name not in certs:
            certs.append(name)
    points = []
    for p in list(o.get("loopSellingPoints") or []) + list(o.get("sellPointsBeforeProductCertificates") or []):
        t = _text(p.get("text")) if isinstance(p, dict) else _text(p)
        if t and t not in points:
            points.append(t)
    fulfillment = _text(o.get("fulfillmentInfo"))
    if fulfillment and fulfillment not in points:
        points.append(fulfillment)
    if o.get("halfTrust"):
        is_guaranteed = True
    images = []
    for img in ([o.get("mainImage")] + list(o.get("multiImage") or [])):
        u = _image(img)
        if u and u not in images:
            images.append(u)
    supplier_link = _link(o.get("supplierHomeHref"))
    return {
        "id": pid,
        "title": _text(o.get("title")),
        "link": _link(o.get("productUrl")) or f"{BASE}/product-detail/_{pid}.html",
        "image": images[0] if images else None,
        "images": images,
        "price": price,
        "promotion_price": promo,
        "discount": _text(o.get("discount")),
        "moq": parse_moq(o.get("moq") or o.get("moqV2")),
        "sold_count": sold,
        "rating": {
            "product_score": _float(o.get("productScore")),
            "review_score": _float(o.get("reviewScore")),
            "review_count": _count(o.get("reviewCount")),
            "supplier_service_score": _float(o.get("supplierServiceScore") or o.get("supplierService")),
            "shipping_score": _float(o.get("shippingScore") or o.get("shippingTime")),
            "star_level": _int(o.get("displayStarLevel")),
        },
        "supplier": {
            "id": _clean_id(o.get("companyId")),
            "name": _text(o.get("companyName")),
            "link": supplier_link,
            "subdomain": _subdomain_of(supplier_link),
            "logo": _image(o.get("companyLogo")),
            "country_code": _text(o.get("countryCode")),
            "years_on_alibaba": _years(o.get("goldSupplierYears")),
            "is_gold_supplier": bool(o.get("goldSupplierIcon")),
            "is_verified_pro": bool(o.get("goldSupplierProIcon")),
        },
        "badges": badges,
        "certifications": certs,
        "selling_points": points,
        "is_alibaba_guaranteed": is_guaranteed,
        "is_customizable": bool(o.get("customizable")),
        "is_ad": bool(o.get("isShowAd") or o.get("isP4P") or o.get("isNewAd")),
    }


def _subdomain_of(link):
    if not link:
        return None
    m = re.match(r"https?://([a-z0-9-]+)\.(?:m\.)?en\.alibaba\.com", link, re.I)
    return m.group(1).lower() if m else None


def _facet_values(values, id_key="id"):
    out = []
    for v in values or []:
        if not isinstance(v, dict):
            continue
        name = _text(v.get("name"))
        if not name:
            continue
        vid = v.get(id_key)
        if isinstance(vid, str) and vid.isdigit():
            vid = int(vid)
        out.append({"id": vid, "name": name, "count": _count(v.get("count"))})
    return out


def _search_filters(sn):
    """The facet blocks of a search page -> available filter values."""
    if not isinstance(sn, dict):
        return None
    cat = sn.get("category") or {}
    related = _facet_values(_dig(cat, "monolayerCategoryData", "values"))
    if not related:
        # catalog pages carry the selected chain instead of siblings
        chain = _dig(cat, "categoryGalleryData", 0, "values") or []
        related = _flatten_chain(chain)
    countries = []
    for v in _dig(sn, "supplierLocation", "countrySupplierLocation") or []:
        if isinstance(v, dict) and v.get("id"):
            countries.append({"code": v.get("id"), "name": _text(v.get("name")), "count": _count(v.get("count"))})
    features = []
    for f in _dig(sn, "productFeature", "productFeatureData") or []:
        if not isinstance(f, dict):
            continue
        features.append({
            "id": _dig(f, "title", "id"),
            "name": _text(_dig(f, "title", "name")),
            "values": _facet_values(f.get("values")),
        })
    return {
        "related_categories": related,
        "supplier_countries": countries,
        "supplier_certifications": _facet_values(_dig(sn, "snCompanyAuthTagResult", "companyAuthTagData", 0, "values")),
        "product_certifications": _facet_values(_dig(sn, "snProductAuthTagResult", "productAuthTagData", 0, "values")),
        "product_features": features,
    }


def _flatten_chain(nodes, out=None):
    out = [] if out is None else out
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        if n.get("id") not in (None, "", "null"):
            out.append({"id": _clean_id(n.get("id")), "name": _text(n.get("name")),
                        "count": _count(n.get("count")), "is_selected": bool(n.get("checked"))})
        _flatten_chain(n.get("childs"), out)
    return out


def parse_search_page(blob, page, currency=None):
    """window.__page__data_sse10._offer_list -> {"pagination", "count",
    "results", "filters"}. `blob` None/{} means the page rendered no offer
    list (past the last page, or the empty-result shell)."""
    blob = blob or {}
    ord_ = blob.get("offerResultData") or {}
    raw = ord_.get("offers") or []
    results = [c for c in (_offer_card(o, currency) for o in raw) if c]
    total = _count(ord_.get("totalCount"))
    page_count = _int(_dig(ord_, "paginationData", "pageCount")) or SEARCH_MAX_PAGES
    pagination = _pagination(page, SEARCH_PAGE_SIZE, total, max_pages=min(page_count, SEARCH_MAX_PAGES))
    if results and pagination["total_pages"] < page:
        pagination["total_pages"] = page
    corrected = _dig(blob, "queryErrCorrectionData", "correctedKeyword") or _dig(blob, "queryErrCorrectionData", "correctKeyword")
    return {
        "keyword": _text(blob.get("keyword")),
        "corrected_keyword": _text(corrected),
        "pagination": pagination,
        "count": len(results),
        "results": results,
        "filters": _search_filters(blob.get("snData")),
    }


IMAGE_PAGE_SIZE = 20


def parse_image_search_page(data, page):
    """open-s imageSearchViewService `data` -> same card shape as a keyword
    search plus the detected crop regions and the category facet. The
    gateway reports no total; `total_pages` is page+1 while a full page came
    back (walk until an empty page / 404)."""
    data = data or {}
    raw = data.get("offers") or []
    results = [c for c in (_offer_card(o, data.get("localCurrency")) for o in raw) if c]
    total = _count(data.get("totalCount"))
    page_count = _int(data.get("pageCount")) or 0
    if total:
        total_pages = math.ceil(total / IMAGE_PAGE_SIZE)
    elif page_count:
        total_pages = page_count
    else:
        total_pages = page + 1 if len(results) >= IMAGE_PAGE_SIZE else (page if results else 0)
    cats = []
    for c in data.get("allCategories") or []:
        if not isinstance(c, dict) or str(c.get("id")) == "66666666":   # "All"
            continue
        cats.append({"id": _clean_id(c.get("id")), "name": _text(c.get("name")), "is_selected": bool(c.get("selected"))})
    return {
        "pagination": {"page": page, "items_per_page": IMAGE_PAGE_SIZE, "total_pages": total_pages,
                       "total_count": total},
        "count": len(results),
        "results": results,
        "input_image": _link(data.get("originalImageUrl")),
        "regions": [r for r in (data.get("regions") or []) if isinstance(r, str) and r],
        "selected_region": _text(data.get("selectRegion")),
        "filters": {"categories": cats},
    }


# ---- supplier search (window._PAGE_DATA_) ---------------------------------

def _supplier_card(o):
    if not isinstance(o, dict):
        return None
    cid = _clean_id(o.get("companyId"))
    if not cid:
        return None
    link = _link(o.get("action"))
    sub = _subdomain_of(link)
    main = o.get("mainProduct") if isinstance(o.get("mainProduct"), dict) else {}
    products = [p.strip() for p in (o.get("provideProducts") or "").split(",") if p.strip()]
    return {
        "id": cid,
        "name": _text(o.get("companyName")),
        "link": f"https://{sub}.en.alibaba.com/" if sub else link,
        "subdomain": sub,
        "logo": _image(o.get("companyIcon")),
        "images": [u for u in (_image(i) for i in (o.get("companyImage") or [])) if u],
        "main_products": products,
        "featured_product": {
            "id": _clean_id(main.get("id")),
            "title": _text(main.get("title") or main.get("subject")),
            "link": _link(main.get("action") or main.get("landingPage")),
            "image": _image(main.get("imageUrl")),
            "price": parse_price(main.get("price")),
        } if main else None,
        "years_on_alibaba": _years(o.get("goldYears")),
        "factory_area": _text(o.get("area")),
        "staff": _text(o.get("staff")),
        "transactions": _text(o.get("transactions")),
        "response_time": _text(o.get("replyAvgTime")),
        "rating": {
            "score": _float(o.get("reviewScore")),
            "review_count": _count(o.get("reviewCount")),
            "link": _link(o.get("reviewLink")),
        },
        "tags": [t for t in (_text(x.get("text") if isinstance(x, dict) else x) for x in (o.get("tag") or [])) if t],
        "is_verified_supplier": bool(o.get("isAssessedSupplier")),
        "is_verified_pro": bool(o.get("verifiedSupplierPro")),
        "has_live_stream": bool(o.get("hasLive")),
        "is_ad": bool(o.get("newAd")),
    }


def parse_supplier_search_page(blob, page):
    blob = blob or {}
    ord_ = blob.get("offerResultData") or {}
    raw = ord_.get("offerList") or []
    results = [c for c in (_supplier_card(o) for o in raw) if c]
    total = _count(ord_.get("totalCount"))
    per_page = _int(ord_.get("pageSize")) or SUPPLIER_PAGE_SIZE
    pagination = _pagination(page, per_page, total, max_pages=SEARCH_MAX_PAGES)
    if results and pagination["total_pages"] < page:
        pagination["total_pages"] = page
    sn = blob.get("snData") or {}
    countries = [{"code": v.get("id"), "name": _text(v.get("name")), "count": _count(v.get("count"))}
                 for v in (_dig(sn, "supplierLocation", "countrySupplierLocation") or []) if isinstance(v, dict) and v.get("id")]
    return {
        "keyword": _text(blob.get("keyword")),
        "pagination": pagination,
        "count": len(results),
        "results": results,
        "filters": {
            "supplier_countries": countries,
            "supplier_certifications": _facet_values(_dig(sn, "snCompanyAuthTagResult", "companyAuthTagData", 0, "values")),
            "product_certifications": _facet_values(_dig(sn, "snProductAuthTagResult", "productAuthTagData", 0, "values")),
        },
    }


# ---- product details (window.detailData) -----------------------------------

def _attr_list(items):
    out = []
    for a in items or []:
        if not isinstance(a, dict):
            continue
        name = _text(a.get("attrName") or a.get("attribute") or a.get("name"))
        value = _text(a.get("attrValue") or a.get("value"))
        if name:
            out.append({"name": name, "value": value})
    return out


def _ladder(prices):
    out = []
    for p in prices or []:
        if not isinstance(p, dict):
            continue
        out.append({
            "min_quantity": _int(p.get("min")),
            "max_quantity": _int(p.get("max")) if _int(p.get("max")) not in (None, -1, 0) else None,
            "price": _float(p.get("price")),
            "price_usd": _float(p.get("dollarPrice")),
            "formatted": _text(p.get("formatPrice")),
        })
    return out


def _variants(sku):
    attrs = []
    for a in (sku or {}).get("skuAttrs") or []:
        if not isinstance(a, dict):
            continue
        values = []
        for v in a.get("values") or []:
            if not isinstance(v, dict):
                continue
            values.append({
                "id": _clean_id(v.get("id")),
                "name": _text(v.get("name")),
                "image": _image(v.get("originImage") or v.get("largeImage")),
                "color": _text(v.get("color")),
            })
        attrs.append({"id": _clean_id(a.get("id")), "name": _text(a.get("name")),
                      "type": _text(a.get("type")), "values": values})
    skus = []
    for key, info in ((sku or {}).get("skuInfoMap") or {}).items():
        if not isinstance(info, dict):
            continue
        pairs = []
        for part in str(key).strip(";").split(";"):
            if ":" in part:
                aid, vid = part.split(":", 1)
                pairs.append({"attribute_id": _clean_id(aid), "value_id": _clean_id(vid)})
        entry = {"id": _clean_id(info.get("id")), "attribute_values": pairs}
        # SKU-priced listings carry the price per SKU instead of a ladder
        if info.get("price") is not None:
            entry["price"] = _float(info.get("price"))
            entry["price_usd"] = _float(info.get("dollarPrice"))
            entry["promotion_price"] = _float(info.get("promotionPrice"))
            entry["formatted"] = _text(info.get("formatPrice"))
        skus.append(entry)
    return {"attributes": attrs, "skus": skus} if attrs or skus else None


def _inventory(inv, skus):
    if not isinstance(inv, dict):
        return None
    places = [{"id": p.get("id"), "name": _text(p.get("name"))}
              for p in (inv.get("placeOfDispatches") or []) if isinstance(p, dict)]
    per_sku = {}
    for sid, data in (inv.get("skuInventory") or {}).items():
        total = None
        for w in (data or {}).get("warehouseInventoryList") or []:
            n = _int(w.get("inventoryCount"))
            if n is not None and n >= 0:      # -1 = made to order / not tracked
                total = (total or 0) + n
        per_sku[str(sid)] = total
    for s in skus or []:
        if s.get("id") is not None:
            s["stock"] = per_sku.get(str(s["id"]))
    return {
        "ships_from": places,
        "default_dispatch": inv.get("defaultDispatchId"),
        "total_stock": sum(v for v in per_sku.values() if v is not None) if any(v is not None for v in per_sku.values()) else None,
    }


def _lead_times(trade):
    out = []
    for l in _dig(trade, "leadTimeInfo", "ladderPeriodList") or []:
        if isinstance(l, dict):
            out.append({"min_quantity": _int(l.get("minQuantity")),
                        "max_quantity": _int(l.get("maxQuantity")),
                        "days": _int(l.get("processPeriod"))})
    return out


def _certifications(certs):
    out = []
    for c in certs or []:
        if not isinstance(c, dict):
            continue
        summary = c.get("summary") if isinstance(c.get("summary"), dict) else {}
        out.append({
            "id": _clean_id(c.get("certId")),
            "name": _text(c.get("certName")),
            "number": _text(c.get("certNo")),
            "type": _text(c.get("certType")),
            "owner_type": _text(c.get("certOwnType")),
            "validity_period": _text(c.get("certValidPeriod")),
            "issuing_authority": _text(c.get("issuingAuthority")),
            "images": [u for u in (_image(i) for i in (c.get("imageList") or [])) if u],
            "description": _text(c.get("introduction")),
            "applicable_regions": _text(summary.get("applicableRegions")),
            "applicable_industry": _text(summary.get("applicableIndustry")),
            "standard": _text(summary.get("certificationStandard")),
        })
    return out


def _description(pd):
    """module_description.privateData -> structured description."""
    if not isinstance(pd, dict):
        return None

    def blocks(section):
        out = []
        for d in (_dig(pd, section, "details") or []):
            if not isinstance(d, dict):
                continue
            t = d.get("type")
            if t == "text":
                txt = _text(d.get("text"))
                if txt:
                    out.append({"type": "text", "text": txt})
            elif t in ("image", "img"):
                out.append({"type": "image", "link": _image(d.get("imageUrl") or d.get("url") or d.get("src"))})
            elif t == "qa":
                out.append({"type": "qa", "question": _text(d.get("question")), "answer": _text(d.get("answer"))})
            elif t == "video":
                out.append({"type": "video", "link": _link(d.get("url") or d.get("videoUrl")), "video_id": d.get("videoId")})
            else:
                txt = _text(d.get("text") or d.get("value"))
                if txt:
                    out.append({"type": t or "text", "text": txt})
        return out

    faq = [{"question": b["question"], "answer": b["answer"]} for b in blocks("faqInfo") if b.get("type") == "qa"]
    company_images = []
    for grp in _dig(pd, "companyInfo", "imageSetDetails") or []:
        for d in (grp.get("details") or []) if isinstance(grp, dict) else []:
            u = _image(d.get("imageUrl") or d.get("url")) if isinstance(d, dict) else None
            if u:
                company_images.append(u)
    return {
        "details": blocks("productDescription"),
        "specification": blocks("specification"),
        "packing": blocks("packingLogistics"),
        "faq": faq,
        "about_supplier": {
            "text": " ".join(b["text"] for b in blocks("companyInfo") if b.get("text")) or None,
            "images": company_images,
        },
        "video_id": _dig(pd, "productDescription", "videoId"),
    }


def _shipping(pd):
    if not isinstance(pd, dict):
        return None
    options = []
    for group in pd.get("logisticsList") or []:
        for item in (group.get("listData") or []) if isinstance(group, dict) else []:
            if not isinstance(item, dict):
                continue
            options.append({
                "method": _text(item.get("method")),
                "type": _text(item.get("shippingType")),
                "price": _text(item.get("price")),
                "original_price": _text(item.get("originalPrice")),
                "delivery": _text(item.get("deliveredDate") or item.get("deliveredRangeDate")),
                "is_alibaba_logistics": bool(item.get("showAliLogisticsLogo")),
            })
    deliver_to = _text(_dig(pd, "deliverInfo", "text"))
    m = re.search(r"Deliver to\s+([A-Za-z ]+)$", deliver_to or "")
    return {"deliver_to": (m.group(1).strip() if m else deliver_to), "options": options}


def _samples(pd):
    """module_sample_new.privateData -> the price floor block. Two shapes:
    ladder listings carry priceList[{minQuantity,maxQuantity,price}], SKU-
    priced listings carry priceList[{minPrice,maxPrice,formatOriginalPrice}]
    plus discountInfo / promotionDX."""
    if not isinstance(pd, dict):
        return None
    ladder = []
    for p in pd.get("priceList") or []:
        if not isinstance(p, dict):
            continue
        if "minPrice" in p or "maxPrice" in p:
            ladder.append({"min_quantity": None, "max_quantity": None,
                           "min_price": _float(p.get("minPrice")), "max_price": _float(p.get("maxPrice")),
                           "formatted": _text(p.get("formatPrice")),
                           "original_formatted": _text(p.get("formatOriginalPrice"))})
        else:
            ladder.append({"min_quantity": _int(p.get("minQuantity")),
                           "max_quantity": _int(p.get("maxQuantity")) if _int(p.get("maxQuantity")) not in (None, -1, 0) else None,
                           "price": _float(p.get("price")), "formatted": _text(p.get("formatPrice"))})
    mo = _dig(pd, "orderQuantity", "minOrder") or {}
    stock = _dig(pd, "orderQuantity", "stock") or {}
    return {
        "min_order": {"quantity": _count(mo.get("minOrderQuantity")), "unit": _text(mo.get("quantityUnit"))} if mo else None,
        "stock": _count(stock.get("stockNum")) if stock else None,
        "price_ladder": ladder,
    }


def _promotion(pd, price):
    """Active discount: module_sample_new.discountInfo/promotionDX or the
    promotion range on price.productRangePrices."""
    info = _dig(pd, "discountInfo") if isinstance(pd, dict) else None
    rng = price.get("productRangePrices") if isinstance(price, dict) else None
    if not info and not (rng and rng.get("pricePromotionRangeText")):
        return None
    info = info or {}
    ends = _int(info.get("endTime"))
    return {
        "text": _text(info.get("text")) or _text(_dig(pd, "promotionDX", "promotionContent")),
        "discount_percent": _float(info.get("discountRate")),
        "min_price": _float((rng or {}).get("priceRangePromotionLow")),
        "max_price": _float((rng or {}).get("priceRangePromotionHigh")),
        "formatted": _text((rng or {}).get("pricePromotionRangeText")),
        "starts_at": datetime.fromtimestamp(_int(info["startTime"]) / 1000, timezone.utc).strftime("%Y-%m-%d") if _int(info.get("startTime")) else None,
        "ends_at": datetime.fromtimestamp(ends / 1000, timezone.utc).strftime("%Y-%m-%d") if ends else None,
    }


def _auth_groups(seller):
    groups = _dig(seller, "authCards", "value", "authGroupInfoList") or []
    out = {}
    for g in groups:
        if not isinstance(g, dict):
            continue
        items = []
        for a in g.get("authInfoList") or []:
            if isinstance(a, dict) and a.get("authName"):
                items.append({"name": _text(a.get("authName")), "value": _text(a.get("authValue")),
                              "description": _text(a.get("authDesc"))})
        if items:
            out[_snake(g.get("authGroup"))] = items
    return out or None


def _snake(name):
    if not name:
        return "other"
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", str(name)).lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _seller(seller, card, review):
    if not isinstance(seller, dict):
        return None
    sub = _text(seller.get("subDomain"))
    if sub and sub.endswith(".en.alibaba.com"):
        sub = sub[: -len(".en.alibaba.com")]
    rating = seller.get("supplierRatingReviews") if isinstance(seller.get("supplierRatingReviews"), dict) else {}
    breakdown = {}
    for l in rating.get("latitudeScoreDTOList") or []:
        if isinstance(l, dict) and l.get("latitudeType"):
            breakdown[_snake(l["latitudeType"])] = _float(l.get("latitudeAverageScore"))
    card = card if isinstance(card, dict) else {}
    markets = [{"country_code": m.get("country"), "name": _text(m.get("countryName")),
                "share": _float(m.get("percentage"))}
               for m in (_dig(card, "mainMarkets", "list") or []) if isinstance(m, dict)]
    ranking = _text(_dig(card, "rankingContent", "rankingText"))
    verified = seller.get("verifiedManufactruers") if isinstance(seller.get("verifiedManufactruers"), dict) else {}
    return {
        "id": _clean_id(seller.get("companyId")),
        "name": _text(seller.get("companyName")),
        "link": f"https://{sub}.en.alibaba.com/" if sub else _link(seller.get("homeUrl")),
        "subdomain": sub,
        "logo": _image(seller.get("companyLogoFileUrlSmall")),
        "country_code": _text(seller.get("companyRegisterCountry")),
        "location": (lambda t: re.sub(r"^Located in\s+", "", t) if t else None)(_text(_dig(card, "locationInfo", "location"))),
        "business_type": [t.strip() for t in (seller.get("companyBusinessType") or "").split(",") if t.strip()],
        "years_on_alibaba": _int(seller.get("companyJoinYears")),
        "employees": _text(seller.get("employeesCount")),
        "response_time": _text(seller.get("responseTimeText")),
        "on_time_delivery_rate": _percent(seller.get("supplierOnTimeDeliveryRate")),
        "rating": {
            "average": _float(rating.get("averageStar")),
            "review_count": _count(rating.get("totalReviewOrderCount")),
            "breakdown": breakdown or None,
        },
        "transactions": {
            "half_year_order_amount": _text(_dig(seller, "tradeHalfYear", "ordAmt")),
            "half_year_order_amount_usd": _float(_dig(seller, "tradeHalfYear", "ordAmt6m")),
            "half_year_order_count": _count(_dig(seller, "tradeHalfYear", "ordCnt6m")),
        },
        "trade_assurance_amount": _text(seller.get("baoAccountAmount")),
        "verified_label": _text(verified.get("text")),
        "ranking": ranking,
        "main_markets": markets,
        "services": [_text(x) for x in (_dig(card, "serviceCapacity", "items") or []) if _text(x)],
        "quality_control": [_text(x) for x in (_dig(card, "qualityAssuranceCapability", "items") or []) if _text(x)],
        "capabilities": _auth_groups(seller),
        "contact": {"name": _text(seller.get("contactName")), "job_title": _text(seller.get("jobTitle"))},
        "is_verified_supplier": bool(seller.get("companyHasPassAssessment")),
        "is_gold_supplier": bool(seller.get("accountIsGoldPlusSupplier")),
        "is_trade_assurance": bool(seller.get("baoAccountIsService")),
        "is_verified_manufacturer": bool(verified),
        "has_video_chat": bool(seller.get("hasVideoChat")),
    }


def product_page_is_missing(html, blob):
    """The 'Product Not Available' page still ships a detailData blob but no
    product id."""
    if "<title>Product Not Available</title>" in (html or "")[:20000]:
        return True
    return not _dig(blob or {}, "globalData", "product", "productId")


def parse_product_page(blob, currency=None):
    g = (blob or {}).get("globalData") or {}
    nm = (blob or {}).get("nodeMap") or {}
    p = g.get("product") or {}
    trade = g.get("trade") or {}
    price = p.get("price") if isinstance(p.get("price"), dict) else {}
    pattern = _text(_dig(price, "currencyRule", "currencyPattern")) or ""
    cur = _currency_from_symbol(pattern.replace("{0}", "1"), currency)
    ladder = _ladder(price.get("productLadderPrices"))
    # SKU-priced listings: one price range instead of a quantity ladder
    rng = price.get("productRangePrices") if isinstance(price.get("productRangePrices"), dict) else {}
    price_min = min((l["price"] for l in ladder if l.get("price") is not None), default=None)
    price_max = max((l["price"] for l in ladder if l.get("price") is not None), default=None)
    if price_min is None and rng:
        price_min = _float(rng.get("priceRangeLow"))
        price_max = _float(rng.get("priceRangeHigh"))
    formatted = _text(price.get("formatLadderPrice")) or _text(rng.get("priceRangeText"))
    pid = _clean_id(p.get("productId"))
    images = []
    video = None
    for m in p.get("mediaItems") or []:
        if not isinstance(m, dict):
            continue
        if m.get("type") == "image":
            u = _image(_dig(m, "imageUrl", "big") or _dig(m, "imageUrl", "normal"))
            if u and u not in images:
                images.append(u)
    if isinstance(p.get("video"), dict) and p["video"].get("videoId"):
        video = {"id": p["video"].get("videoId"), "cover": _image(p["video"].get("cover"))}
    variants = _variants(p.get("sku"))
    inventory = _inventory(g.get("inventory"), (variants or {}).get("skus"))
    path = [{"id": _clean_id(_dig(c, "hrefObject", "url") and re.search(r"categoryId=(\d+)", _dig(c, "hrefObject", "url") or "") and re.search(r"categoryId=(\d+)", _dig(c, "hrefObject", "url")).group(1)),
             "name": _text(_dig(c, "hrefObject", "name"))}
            for c in (_dig(g, "seo", "breadCrumb", "pathList") or []) if isinstance(c, dict)]
    key_attrs = _attr_list(_dig(nm, "module_3_tab_key_attribute", "privateData", "attributeList")) or \
        _attr_list(p.get("productKeyIndustryProperties"))
    glance = [{"highlight": _text(i.get("highlightText")), "description": _text(i.get("descriptionText"))}
              for i in (_dig(nm, "module_3_tab_glance", "privateData", "items") or []) if isinstance(i, dict)]
    review = g.get("review") or {}
    logistics = trade.get("logisticInfo") if isinstance(trade.get("logisticInfo"), dict) else {}
    return {
        "id": pid,
        "title": _text(p.get("subject")),
        "link": f"{BASE}/product-detail/_{pid}.html" if pid else None,
        "category": {
            "id": _clean_id(p.get("productCategoryId")),
            "leaf_id": _clean_id(p.get("productLeafId")),
            "top_level_id": _clean_id(p.get("firstLevelCateId")),
            "path": path,
        },
        "price": {
            "currency": cur,
            "min": price_min,
            "max": price_max,
            "min_usd": _float(rng.get("dollarPriceRangeLow")) if rng else (ladder[-1].get("price_usd") if ladder else None),
            "max_usd": _float(rng.get("dollarPriceRangeHigh")) if rng else (ladder[0].get("price_usd") if ladder else None),
            "formatted": formatted,
            "unit": _text(price.get("unit")),
            "ladder": ladder,
            "is_per_sku": bool(rng) and not ladder,
            "promotion": _promotion(_dig(nm, "module_sample_new", "privateData"), price),
            "sale_type": _text(price.get("saleType")),
            "price_type": _text(_dig(trade, "tradeInfo", "tradePriceType")),
        },
        "moq": {"quantity": _int(p.get("moq")), "unit": _text(price.get("unitEven") or price.get("unit"))},
        "images": images,
        "video": video,
        "highlights": glance,
        "key_attributes": key_attrs,
        "attributes": _attr_list(p.get("productBasicProperties")),
        "other_attributes": _attr_list(p.get("productOtherProperties")),
        "variants": variants,
        "inventory": inventory,
        "lead_time": _lead_times(trade),
        "packaging": {
            "unit_size": _text(logistics.get("unitSize")),
            "unit_weight_kg": _float(logistics.get("unitWeight")),
            "unit_volume": _text(logistics.get("unitVolume")),
            "properties": _attr_list(logistics.get("productPackagingProperties")),
        },
        "sales": {
            "sold_count": _count(trade.get("salesVolume")),
            "sold_text": _text(trade.get("salesVolume")),
        },
        "rating": {
            "average": _float(_dig(review, "productReview", "averageStar")),
            "review_count": _count(_dig(review, "productReview", "totalReviewCount")),
        },
        "certifications": _certifications(g.get("certification")),
        "samples": _samples(_dig(nm, "module_sample_new", "privateData")),
        "shipping": _shipping(_dig(nm, "module_shipping", "privateData")),
        "description": _description(_dig(nm, "module_description", "privateData")),
        "supplier": _seller(g.get("seller"), _dig(nm, "module_unifed_company_card", "privateData"), review),
        "ships_from_country": _text(p.get("deliverPlace")),
        "is_customizable": bool(p.get("supportLightCustomization") or p.get("supportFastCustomization")),
        "is_ready_to_ship": not bool(p.get("notShowRts")),
        "is_trade_assurance": bool(trade.get("globalTradeAssuranceForBuyer")),
        "is_tariff_included": bool(p.get("tariffIncluded")),
        "is_available": bool(p.get("tradable") if p.get("tradable") is not None else pid),
    }


# ---- reviews (mtop.alibaba.icbu.review.media.review) ----------------------

def _review(r):
    if not isinstance(r, dict):
        return None
    user = r.get("simpleReviewUserVO") if isinstance(r.get("simpleReviewUserVO"), dict) else {}
    prod = r.get("productInfo") if isinstance(r.get("productInfo"), dict) else {}
    media = [{"type": m.get("type"), "link": _link(m.get("url"))}
             for m in (r.get("mediaList") or []) if isinstance(m, dict) and m.get("url")]
    content = _text(r.get("reviewContent"))
    original = _text(r.get("oriReviewContent"))
    reply = _text(r.get("replyContent"))
    reply_original = _text(r.get("oriReplyContent"))
    return {
        "id": _clean_id(r.get("reviewId")),
        "rating": _float(_dig(r, "latitudeScore", "score")),
        "content": content,
        "original_content": original if original and original != content else None,
        "date": _iso_date(r.get("reviewTime")),
        "media": media,
        "reviewer": {
            "name": _text(user.get("anonymousName")),
            "country_code": _text(user.get("country")),
            "country": _text(user.get("fullNameCountry")),
            "is_verified_purchase": bool(user.get("purchased")),
        },
        "supplier_reply": {
            "content": reply,
            "original_content": reply_original if reply_original and reply_original != reply else None,
            "date": _iso_date(r.get("replyTime")),
        } if reply else None,
        "product": {
            "id": _clean_id(prod.get("id")),
            "title": _text(prod.get("title")),
            "link": _link(prod.get("pcProductUrl")),
            "image": _image(prod.get("image")),
            "price": parse_price(prod.get("price")),
            "attributes": [
                {"name": _text(a.get("key") or a.get("name") or a.get("attrName")),
                 "value": _text(a.get("value") or a.get("attrValue"))}
                for a in (prod.get("attributes") or []) if isinstance(a, dict)],
        } if prod else None,
        "helpful_count": _count(r.get("rateCnt")),
    }


def parse_reviews(data, page, page_size):
    data = data or {}
    if "target" not in data and isinstance(data.get("data"), dict):
        data = data["data"]          # full mtop envelope was passed
    target = data.get("target") or {}
    raw = target.get("productReviewVOList") or []
    results = [x for x in (_review(r) for r in raw) if x]
    total = _count(target.get("totalReviewCount")) or 0
    pagination = _pagination(page, page_size, total)
    if results and pagination["total_pages"] < page:
        pagination["total_pages"] = page
    return {"pagination": pagination, "count": len(results), "results": results}


# ---- suggestions / trending ---------------------------------------------------

def parse_suggestions(payload, query):
    items = []
    for s in _dig(payload, "data", "list") or []:
        kw = _text(s.get("suggestKeyword")) if isinstance(s, dict) else None
        if kw:
            items.append({"keyword": kw, "link": f"{BASE}/trade/search?SearchText={kw.replace(' ', '+')}"})
    return {"query": query, "count": len(items), "results": items}


def parse_trending(payload):
    items = []
    for s in _dig(payload, "data", "list") or []:
        kw = _text(s.get("query")) if isinstance(s, dict) else None
        if kw:
            items.append({"keyword": kw, "link": f"{BASE}/trade/search?SearchText={kw.replace(' ', '+')}"})
    return {"count": len(items), "results": items}


# ---- categories (insights gateway) ----------------------------------------

def _category_node(c):
    if not isinstance(c, dict):
        return None
    cid = _clean_id(c.get("categoryIds"))
    return {
        "id": cid,
        "name": _text(c.get("title")) or _text(c.get("titleEn")),
        "link": f"{BASE}/catalog/x_cid{cid}" if cid else _link(c.get("action")),
        "image": _image(c.get("imageUrl")),
        "children": [n for n in (_category_node(x) for x in (c.get("list") or [])) if n],
    }


def parse_category_tree(payload):
    groups = []
    seen = set()
    flat = []
    for tab in _dig(payload, "data", "allCategory", "list") or []:
        if not isinstance(tab, dict):
            continue
        cats = [n for n in (_category_node(c) for c in (tab.get("list") or [])) if n]
        groups.append({"group": _text(tab.get("tabName") or tab.get("titleEn")), "categories": cats})
        for c in cats:
            if c["id"] and c["id"] not in seen:
                seen.add(c["id"])
                flat.append(c)
    return {"count": len(flat), "results": flat, "groups": groups}


def parse_category_children(payload, parent_id):
    cats = [n for n in (_category_node(c) for c in (_dig(payload, "data", "list") or [])) if n]
    return {"parent_id": parent_id, "count": len(cats), "results": cats}


# ---- store pages (module-data attributes) ----------------------------------

def _module(modules, name):
    for m in modules or []:
        if m.get("module_name") == name:
            return _dig(m, "mds", "moduleData", "data") or {}
    return {}


def _module_gdc(modules):
    for m in modules or []:
        if isinstance(m.get("gdc"), dict):
            return m["gdc"]
    return {}


def _fv(obj, *keys):
    """Value of a {fieldName, value} wrapper or a plain scalar."""
    cur = _dig(obj, *keys)
    if isinstance(cur, dict):
        # {fieldName, title, value} wrapper; a wrapper without `value` means
        # the supplier did not disclose that field
        if "value" in cur:
            return cur.get("value")
        if "fieldName" in cur or "title" in cur:
            return None
    return cur


def parse_store_home(modules, subdomain):
    gdc = _module_gdc(modules)
    sign = _module(modules, "icbu-pc-shopSign")
    over = _module(modules, "icbu-pc-companyOverview")
    if not gdc and not sign:
        return None
    cid = _clean_id(gdc.get("companyId") or _fv(sign, "companyId"))
    main_products = _fv(sign, "supplierMainProducts")
    if isinstance(main_products, list):
        main_products = [_text(x.get("name") if isinstance(x, dict) else x) for x in main_products]
        main_products = [x for x in main_products if x]
    elif isinstance(main_products, str):
        main_products = [x.strip() for x in main_products.split(",") if x.strip()]
    else:
        main_products = []
    over_products = _fv(over, "supplierMainProducts")
    if not main_products and isinstance(over_products, str):
        main_products = [x.strip() for x in over_products.split(",") if x.strip()]
    ability = []
    for t in (_dig(sign, "companyAbilityTags", "resultMapList") or []):
        name = _text(t.get("tagName") or t.get("name") or t.get("text")) if isinstance(t, dict) else _text(t)
        if name:
            ability.append(name)
    identity = _fv(sign, "authIdentityInfo") or {}
    cert_co = _fv(sign, "assessmentCertCompany") or _fv(over, "assessmentCertCompany") or {}
    about_imgs = _fv(over, "supplierAboutUsImg") or []
    return {
        "id": cid,
        "name": _text(sign.get("companyName") or _fv(over, "companyName")),
        "link": f"https://{subdomain}.en.alibaba.com/",
        "subdomain": subdomain,
        "logo": _image(sign.get("companyLogoFileUrl")),
        "country_code": _text(sign.get("companyRegisterCountry")),
        "province": _text(_fv(sign, "companyRegisterProvince")),
        "location": _text(_fv(sign, "companyLocation") or _fv(over, "companyLocation")),
        "address": _text(_fv(sign, "supplierOperationalAddress")),
        "business_type": [t.strip() for t in str(_fv(sign, "companyBusinessType") or _fv(over, "companyBusinessType") or "").split(",") if t.strip()],
        "years_on_alibaba": _int(_fv(sign, "accountJoinYears")),
        "established_year": _int(_fv(over, "companyEstablishedYear")),
        "employees": _text(_fv(over, "companyNumberOfEmployees")),
        "staff_count": _int(_fv(sign, "authStaffNo")),
        "supplier_stars": _int(sign.get("supplierStars")),
        "main_products": main_products,
        "main_markets": [m.strip() for m in str(_fv(over, "companyMainMarket") or "").split(",") if m.strip()],
        "description": _text(_fv(over, "companyDescription") or _fv(over, "supplierAdvantageDescription")),
        "about_images": [u for u in (_image(i) for i in (about_imgs if isinstance(about_imgs, list) else [])) if u],
        "video_cover": _image(_fv(over, "companyVideoPicturePath")),
        "management_certifications": [c.strip() for c in str(_fv(over, "companyManagementCertificatesName") or "").split(",") if c.strip()],
        "total_annual_revenue": _text(_fv(over, "companyTotalRevenue")),
        "accepted_payment_methods": [c.strip() for c in str(_fv(over, "supplierAcceptedPaymentType") or "").split(",") if c.strip()],
        "accepted_currencies": [c.strip() for c in str(_fv(over, "supplierAcceptedPaymentCurrency") or "").split(",") if c.strip()],
        "accepted_delivery_terms": [c.strip() for c in str(_fv(over, "supplierAcceptedDeliveryTerms") or "").split(",") if c.strip()],
        "contract_manufacturing": [_text(x) for x in (_fv(over, "supplierContractManufacturing") or []) if _text(x)] if isinstance(_fv(over, "supplierContractManufacturing"), list) else [],
        "capability_tags": ability,
        "identity": {
            "key": _text(identity.get("identityKey")),
            "name": _text(identity.get("identityName")),
            "description": _text(identity.get("identityDesc")),
        } if isinstance(identity, dict) and identity else None,
        "verification": {
            "assessed_by": _text(cert_co.get("title") or cert_co.get("logoTips")) if isinstance(cert_co, dict) else None,
            "has_supplier_assessment": bool(_fv(sign, "companyHasPassAssessment") if sign.get("companyHasPassAssessment") is not None else _fv(over, "companyHasPassAssessment")),
            "has_onsite_check": bool(sign.get("companyHasPassOnsite") if sign.get("companyHasPassOnsite") is not None else _fv(over, "companyHasPassOnsite")),
            "has_av_check": bool(sign.get("companyHasPassAV") if sign.get("companyHasPassAV") is not None else _fv(over, "companyHasPassAV")),
            "has_verified_video": bool(sign.get("companyHasAssessmentVideo") if sign.get("companyHasAssessmentVideo") is not None else _fv(over, "companyHasAssessmentVideo")),
        },
        "is_gold_supplier": bool(gdc.get("isGold") if gdc.get("isGold") is not None else sign.get("isNewGolden")),
        "is_verified_supplier": bool(_fv(sign, "companyHasPassAssessment") if sign.get("companyHasPassAssessment") is not None else _fv(over, "companyHasPassAssessment")),
        "is_trade_assurance": bool(sign.get("baoAccountIsDisplayAssurance")),
        "is_local_supplier": bool(_fv(sign, "isLocalSupplier")),
        "has_live_stream": bool(_fv(gdc, "liveInStore")),
    }


def parse_store_performance(modules):
    """icbu-pc-verifiedInquery (feedback page) -> performance stats."""
    vi = _module(modules, "icbu-pc-verifiedInquery")
    if not vi:
        return None
    return {
        "response_time": _text(_fv(vi, "supplierResponseTime")),
        "on_time_delivery_rate": _percent(_fv(vi, "supplierOnTimeDeliveryRate")),
        "half_year_order_amount": _text(_fv(vi, "ordAmt")),
        "half_year_order_count": _count(_fv(vi, "ordCnt6m")),
        "has_video_call": bool(_fv(vi, "callMeetingAvailable")),
    }


def _store_product(p):
    if not isinstance(p, dict):
        return None
    pid = _clean_id(p.get("id"))
    if not pid:
        return None
    images = [u for u in (_image(_dig(i, "original")) for i in (p.get("imageUrlList") or []) if isinstance(i, dict)) if u]
    price = parse_price(p.get("fobPriceWithoutUnit"))
    if price and p.get("currencySymbol") and p.get("currencyType"):
        price["currency"] = _currency_from_symbol(p.get("currencySymbol"), price.get("currency"))
    certs = [_text(c.get("name")) for c in (p.get("productCertificateLogos") or []) if isinstance(c, dict) and _text(c.get("name"))]
    return {
        "id": pid,
        "title": _text(p.get("subject")),
        "link": _link(p.get("url")) or f"{BASE}/product-detail/_{pid}.html",
        "image": images[0] if images else None,
        "images": images,
        "price": price,
        "price_unit": _text(p.get("fobUnit")),
        "moq": parse_moq(p.get("moq")),
        "sold_count_180d": _count(p.get("prodSold180")),
        "order_count": _count(p.get("prodOrdCnt")),
        "monthly_views": _count(p.get("duvCntOneMonth")),
        "review_score": _float(p.get("productReviewScore")),
        "certifications": certs,
        "group_id": _clean_id(p.get("groupId")),
        "video_id": p.get("videoId") or None,
        "is_ready_to_ship": bool(p.get("rtsProduct")),
        "is_alibaba_guaranteed": bool(p.get("halfTrust")),
        "is_customizable": bool(p.get("market")),
        "has_fast_dispatch": bool(p.get("quickDelivery")),
    }


def parse_store_products(modules, page, subdomain):
    pl = _module(modules, "icbu-pc-productListPc")
    raw = pl.get("productList") or []
    results = [x for x in (_store_product(p) for p in raw) if x]
    nav = pl.get("pageNavView") if isinstance(pl.get("pageNavView"), dict) else {}
    total = _count(nav.get("totalLines")) or len(results)
    per_page = _int(nav.get("pageLines")) or STORE_PAGE_SIZE
    current = _int(nav.get("currentPage")) or page
    pagination = _pagination(current, per_page, total)
    groups = []
    for g in (_module(modules, "icbu-pc-productGroups").get("groups") or []):
        node = _store_group(g, subdomain)
        if node:
            groups.append(node)
    return {
        "pagination": pagination,
        "count": len(results),
        "results": results,
        "groups": groups,
        "current_group": _text(_dig(pl, "productGroupView", "currentGroupName")),
    }


def _store_group(g, subdomain):
    if not isinstance(g, dict):
        return None
    gid = _clean_id(g.get("id"))
    return {
        "id": gid,
        "name": _text(g.get("name")),
        "link": f"https://{subdomain}.en.alibaba.com{g.get('url')}" if g.get("url") else None,
        "children": [n for n in (_store_group(c, subdomain) for c in (g.get("children") or [])) if n],
    }
