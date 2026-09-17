"""Offline parser tests against real captures (2026-09-14) in alibaba/fixtures/.

    python -m pytest alibaba/test_parsers.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alibaba import parsers  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load(name):
    with open(os.path.join(FX, name)) as f:
        return json.load(f)


# ---- helpers ------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("€2.61-3.38", (2.61, 3.38, "EUR")),
    ("$6.0~7.0", (6.0, 7.0, "USD")),
    ("US $1.20", (1.2, 1.2, "USD")),
    ("₹2,976.80-3,307.34", (2976.8, 3307.34, "INR")),
    ("$575-800", (575.0, 800.0, "USD")),
    ("€0.7933-0.9154", (0.7933, 0.9154, "EUR")),
])
def test_parse_price(text, expected):
    p = parsers.parse_price(text)
    assert (p["min"], p["max"], p["currency"]) == expected
    assert p["formatted"] == text


def test_parse_price_empty():
    assert parsers.parse_price("") is None
    assert parsers.parse_price("Contact for price") is None


@pytest.mark.parametrize("text,expected", [
    ("Min. order: 1.000 pieces", (1000, "pieces")),
    ("Min. order: 1,000 pieces", (1000, "pieces")),
    ("Min. order: 1 piece", (1, "piece")),
    ("100 pieces", (100, "pieces")),
    ("Min. order: 10 packs", (10, "packs")),
])
def test_parse_moq(text, expected):
    m = parsers.parse_moq(text)
    assert (m["quantity"], m["unit"]) == expected


def test_image_suffix_stripped():
    assert parsers._image("//s.alicdn.com/@sc04/kf/Habc.jpg_300x300.jpg") == "https://s.alicdn.com/@sc04/kf/Habc.jpg"
    assert parsers._image("https://sc04.alicdn.com/kf/Hx.png_220x220.png") == "https://sc04.alicdn.com/kf/Hx.png"
    assert parsers._image("https://sc04.alicdn.com/kf/Hx.png") == "https://sc04.alicdn.com/kf/Hx.png"


def test_iso_dates():
    assert parsers._iso_date("2026/07/01") == "2026-07-01"
    assert parsers._iso_date("July 1, 2026") == "2026-07-01"
    assert parsers._iso_date("08-03-2026") == "2026-08-03"   # replyTime is mm-dd-yyyy


# ---- product search -------------------------------------------------------

def test_search_page_filtered():
    r = parsers.parse_search_page(load("catalog_search_bluetooth_filtered.json"), 1, "INR")
    assert r["keyword"] == "bluetooth speaker"
    assert r["pagination"] == {"page": 1, "items_per_page": 48, "total_pages": 26, "total_count": 1214}
    assert r["count"] == 12 == len(r["results"])
    first = r["results"][0]
    assert first["id"] == 1600259287548
    assert first["link"].startswith("https://www.alibaba.com/product-detail/")
    assert first["image"].endswith(".jpg") and "_300x300" not in first["image"]
    assert first["price"] == {"min": 24.53, "max": 29.43, "currency": "INR", "formatted": "₹24.53-29.43"}
    assert first["moq"] == {"quantity": 1000, "unit": "pieces"}
    assert first["sold_count"] == 26600
    assert first["supplier"]["subdomain"] == "sdhrpacking"
    assert first["supplier"]["years_on_alibaba"] == 6
    assert isinstance(first["is_ad"], bool) and isinstance(first["is_customizable"], bool)
    for card in r["results"]:
        assert card["id"] and card["title"] and card["link"]
        assert "<" not in (card["title"] or "")
    f = r["filters"]
    assert f["related_categories"][0] == {"id": 518, "name": "Speakers", "count": 16}
    assert f["supplier_countries"][0]["code"] == "CN"
    assert f["product_features"] and f["product_features"][0]["values"]


def test_search_page_plain_and_pagination_cap():
    r = parsers.parse_search_page(load("catalog_search_bluetooth_p1.json"), 1, None)
    assert r["pagination"]["total_pages"] == 100          # 40032 results, capped at 100 pages
    assert r["results"][0]["price"]["currency"] == "INR"
    assert all(c["supplier"]["id"] for c in r["results"])


def test_category_listing():
    r = parsers.parse_search_page(load("catalog_cid44_p1.json"), 1, "USD")
    assert r["count"] == 8
    assert r["filters"]["related_categories"][-1] == {"id": 44, "name": "Consumer Electronics", "count": None, "is_selected": True}
    # the symbol on the page wins over the requested currency (capture was ₹)
    assert r["results"][0]["price"]["currency"] == "INR"


def test_search_page_empty_blob():
    r = parsers.parse_search_page(None, 3, None)
    assert r["results"] == [] and r["pagination"]["total_pages"] == 0


# ---- supplier search ------------------------------------------------------

def test_supplier_search_page():
    r = parsers.parse_supplier_search_page(load("supplier_search_bluetooth_p1.json"), 1)
    assert r["pagination"] == {"page": 1, "items_per_page": 20, "total_pages": 85, "total_count": 1692}
    s = r["results"][0]
    assert s["id"] == 292322972 and s["subdomain"] == "wwhdz"
    assert s["link"] == "https://wwhdz.en.alibaba.com/"
    assert s["years_on_alibaba"] == 1 and s["is_verified_supplier"] is True
    assert s["rating"] == {"score": 5.0, "review_count": 4, "link": "https://wwhdz.en.alibaba.com/company_profile/feedback.html"}
    assert s["featured_product"]["id"] == 1601668466680
    assert s["main_products"][0] == "Wearable Bluetooth Speaker"
    assert r["filters"]["supplier_countries"]


# ---- product page ---------------------------------------------------------

def test_product_page():
    p = parsers.parse_product_page(load("pdp_1601302079515.json"), None)
    assert p["id"] == 1601302079515 and p["is_available"] is True
    assert p["category"]["path"][-1] == {"id": 518, "name": "Speakers"}
    assert p["price"]["currency"] == "EUR" and p["price"]["min"] == 2.61 and p["price"]["max"] == 3.38
    assert p["price"]["ladder"][0] == {"min_quantity": 6, "max_quantity": 499, "price": 3.38, "price_usd": 3.87, "formatted": "€3.38"}
    assert p["price"]["ladder"][-1]["max_quantity"] is None
    assert p["moq"] == {"quantity": 6, "unit": "pieces"}
    assert len(p["images"]) == 6 and p["video"]["id"] == 384858639044
    assert p["variants"]["attributes"][0]["name"] == "color" and len(p["variants"]["skus"]) == 4
    assert {s["attribute_values"][0]["value_id"] for s in p["variants"]["skus"]} == {-2, -1, 3327837, 3331260}
    assert all(s["stock"] for s in p["variants"]["skus"])
    assert p["inventory"]["ships_from"] == [{"id": "CN", "name": "China"}]
    assert p["lead_time"] == [{"min_quantity": 1, "max_quantity": 10, "days": 7}]
    assert p["packaging"]["unit_weight_kg"] == 0.5 and p["packaging"]["unit_size"] == "18X10X9"
    assert p["sales"]["sold_count"] == 13062
    assert p["rating"] == {"average": 4.8, "review_count": 26}
    assert p["certifications"][0]["name"] == "Declaration of Conformity"
    assert p["samples"]["price_ladder"][-1]["max_quantity"] is None
    assert p["shipping"]["deliver_to"] == "NL" and p["shipping"]["options"][0]["method"] == "Standard"
    assert len(p["description"]["faq"]) == 5 and p["description"]["details"]
    assert p["highlights"][0]["highlight"] == "IPX4 Waterproof"
    assert p["key_attributes"][0] == {"name": "Connection", "value": "Wireless"}
    s = p["supplier"]
    assert s["id"] == 230860282 and s["subdomain"] == "eptusbchina"
    assert s["link"] == "https://eptusbchina.en.alibaba.com/"
    assert s["rating"]["breakdown"] == {"supplier_services": 4.8, "shipping_time": 4.7, "product_quality": 4.9}
    assert s["on_time_delivery_rate"] == 92.6 and s["years_on_alibaba"] == 13
    assert s["main_markets"][0]["country_code"] == "KR"
    assert s["is_verified_supplier"] and s["is_gold_supplier"] and s["is_trade_assurance"]


def test_product_page_missing():
    with open(os.path.join(FX, "pdp_not_available.html")) as f:
        html = f.read()
    assert parsers.product_page_is_missing(html, None)
    assert parsers.product_page_is_missing("<html></html>", {"globalData": {"product": {}}})
    assert not parsers.product_page_is_missing("<html></html>", load("pdp_1601302079515.json"))


# ---- reviews ----------------------------------------------------------------

def test_reviews():
    r = parsers.parse_reviews(load("mtop_reviews_1601302079515_p1.json"), 1, 5)
    assert r["pagination"] == {"page": 1, "items_per_page": 5, "total_pages": 6, "total_count": 26}
    first = r["results"][0]
    assert first["id"] == 6000079561684 and first["rating"] == 5.0
    assert first["date"] == "2026-07-01"
    assert first["reviewer"] == {"name": "S***z", "country_code": "CO", "country": "Colombia", "is_verified_purchase": True}
    assert first["supplier_reply"]["date"] == "2026-08-03"
    assert first["media"][0]["type"] == "image"
    assert first["product"]["attributes"] == [{"name": "color", "value": "Black"}]
    # the inner `data` object works too (what fetch.mtop returns)
    r2 = parsers.parse_reviews(load("mtop_reviews_1601302079515_p1.json")["data"], 1, 5)
    assert r2["count"] == r["count"]


# ---- discovery -------------------------------------------------------------

def test_suggestions_and_trending():
    s = parsers.parse_suggestions(load("suggest_bluetooth.json"), "bluetooth")
    assert s["count"] == 10 and s["results"][0]["keyword"] == "bluetooth smartwatch"
    assert s["results"][0]["link"] == "https://www.alibaba.com/trade/search?SearchText=bluetooth+smartwatch"
    t = parsers.parse_trending(load("popular_in.json"))
    assert t["count"] == 10 and t["results"][1]["keyword"] == "watch"


def test_category_tree_and_children():
    tree = parsers.parse_category_tree(load("categories_10739.json"))
    assert tree["count"] == 49 and tree["results"][0] == {
        "id": 44, "name": "Consumer Electronics", "link": "https://www.alibaba.com/catalog/x_cid44",
        "image": "https://gw.alicdn.com/imgextra/i2/O1CN01lTlEA71idHDZyDnE1_!!6000000004435-2-tps-200-200.png",
        "children": []}
    assert tree["groups"][0]["group"] == "Top categories" and len(tree["groups"]) == 10
    kids = parsers.parse_category_children(load("categories_10813_44.json"), 44)
    assert kids["parent_id"] == 44 and kids["count"] == 16 and kids["results"][0]["id"] == 201928803


# ---- store pages -----------------------------------------------------------

def test_store_home():
    s = parsers.parse_store_home(load("store_home_modules.json"), "eptusbchina")
    assert s["id"] == 230860282 and s["link"] == "https://eptusbchina.en.alibaba.com/"
    assert s["years_on_alibaba"] == 13 and s["established_year"] == 2013 and s["staff_count"] == 54
    assert s["main_products"][:2] == ["Wireless Speaker", "Power Bank"]
    assert s["verification"]["assessed_by"] == "TüVRheinland" and s["verification"]["has_onsite_check"]
    assert s["is_gold_supplier"] and s["is_verified_supplier"] and s["is_trade_assurance"]
    assert s["accepted_payment_methods"][0] == "T/T"
    assert s["address"].startswith("501, Building C")


def test_store_performance_and_products():
    perf = parsers.parse_store_performance(load("store_feedback_modules.json"))
    assert perf == {"response_time": "≤2h", "on_time_delivery_rate": 92.6, "half_year_order_amount": "800,000+",
                    "half_year_order_count": 207, "has_video_call": True}
    r = parsers.parse_store_products(load("store_productlist_modules.json"), 1, "eptusbchina")
    assert r["pagination"] == {"page": 1, "items_per_page": 16, "total_pages": 36, "total_count": 564}
    assert r["count"] == 16
    p = r["results"][0]
    assert p["id"] == 1601613310604 and p["price"] == {"min": 2.69, "max": 2.99, "currency": "USD", "formatted": "$2.69-2.99"}
    assert p["moq"] == {"quantity": 100, "unit": "pieces"} and p["sold_count_180d"] == 235
    assert p["certifications"][0] == "FCC" and p["is_ready_to_ship"] is True
    assert r["groups"][0]["name"] == "hot sales" and r["groups"][0]["children"][0]["link"].startswith("https://eptusbchina.en.alibaba.com/productgrouplist-")


# ---- image search (open-s gateway) ------------------------------------------

def test_image_search_gateway():
    r = parsers.parse_image_search_page(load("image_search_gateway_p1.json")["data"], 1)
    assert r["pagination"] == {"page": 1, "items_per_page": 20, "total_pages": 5, "total_count": 100}
    assert r["count"] == 8 and r["results"][0]["id"] == 1601658617678
    assert r["results"][0]["price"] == {"min": 680.0, "max": 699.0, "currency": "USD", "formatted": "$680-699"}
    assert r["results"][0]["moq"] == {"quantity": 1, "unit": "piece"}
    assert r["input_image"].startswith("https://icbu-picture-sh.oss-cn-shanghai.aliyuncs.com/icbuimgsearch/")
    assert r["regions"][0] == "507,721,148,568" and r["selected_region"] == "507,721,148,568"
    assert r["filters"]["categories"][0] == {"id": 201148910, "name": "PLC, PAC, & Dedicated Controllers", "is_selected": False}
    assert all(c["id"] != 66666666 for c in r["filters"]["categories"])


def test_product_page_sku_priced():
    """Listings priced per SKU carry productRangePrices + per-SKU prices
    instead of a quantity ladder (capture 2026-09-14, 1600431053815)."""
    p = parsers.parse_product_page(load("pdp_1600431053815_sku_priced.json"), "USD")
    assert p["id"] == 1600431053815
    pr = p["price"]
    assert pr["ladder"] == [] and pr["is_per_sku"] is True
    assert (pr["min"], pr["max"], pr["currency"], pr["formatted"]) == (2.87, 3.17, "USD", "$2.87-3.17")
    assert pr["min_usd"] == 2.87 and pr["max_usd"] == 3.17
    assert pr["promotion"]["discount_percent"] == 20.0 and pr["promotion"]["formatted"] == "$2.30-2.54"
    assert pr["promotion"]["ends_at"] == "2026-10-01"
    sku = p["variants"]["skus"][0]
    assert sku["price"] == 3.17 and sku["promotion_price"] == 2.54 and sku["stock"] is None
    assert p["samples"]["price_ladder"][0]["min_price"] == 2.3 and p["samples"]["stock"] == 0
    assert p["supplier"]["subdomain"] == "rgjewelry" and p["rating"]["review_count"] == 38


def test_store_field_wrapper_without_value():
    assert parsers._fv({"x": {"fieldName": "ordAmt", "title": "ordAmt"}}, "x") is None
    assert parsers._fv({"x": {"fieldName": "ordAmt", "value": "800,000+"}}, "x") == "800,000+"
    assert parsers._fv({"x": "plain"}, "x") == "plain"
