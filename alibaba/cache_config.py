"""Cache TTL per /alibaba/* endpoint (cache.py, keyed on the validated
params — marshmallow fills the defaults, so `?page=1` and no `page` share a
row). Same tiers the rapidapi gateway uses for its other marketplaces
(rapidapi/utils/cache_config.py): 1 day for anything carrying prices,
rankings or reviews, 7 days for company profiles, 30 days for suggestions
and taxonomies, 12 h for a chart that the site recomputes daily.
"""
from datetime import timedelta

# Product listings reorder and re-price daily (ads rotate per request, but
# the organic ranking, prices and MOQs move on the site's daily cycle); a
# miss is one cheap curl_cffi page.
PRODUCT_SEARCH_CACHE = timedelta(days=1)
# Category listings: same churn profile as keyword search.
CATEGORY_LISTING_CACHE = timedelta(days=1)
# Reverse image search: the match set is stable, prices inside it are not;
# keyed on the photo URL / image_path, so re-uploads of the same URL hit.
IMAGE_SEARCH_CACHE = timedelta(days=1)
# Product page: price ladder, promotion window, stock and lead time move
# daily.
PRODUCT_DETAIL_CACHE = timedelta(days=1)
# Buyer reviews: new ones land daily and the first page reorders.
REVIEWS_CACHE = timedelta(days=1)
# Supplier search is the only browser-pool surface (3-5 s + a leased Chrome
# per miss); company rankings move slowly, so a day amortizes it well.
SUPPLIER_SEARCH_CACHE = timedelta(days=1)
# Company profile (verification, factory facts, markets, payment terms) is
# near-static; performance stats inside it refresh on the site's own cycle.
SUPPLIER_DETAIL_CACHE = timedelta(days=7)
# A store's product list is edited by the seller and re-priced like search.
SUPPLIER_PRODUCTS_CACHE = timedelta(days=1)
# Search-bar suggestions and the mega-menu category tree hardly change.
AUTOCOMPLETE_CACHE = timedelta(days=30)
CATEGORIES_CACHE = timedelta(days=30)
# Trending keywords are recomputed daily for the egress market.
TRENDING_CACHE = timedelta(hours=12)
