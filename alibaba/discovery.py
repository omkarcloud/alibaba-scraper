"""Discovery endpoints: autocomplete, trending keywords, category tree.

All three are bare JSON gateways (open-s.alibaba.com / insights.alibaba.com)
that answer plain curl_cffi with no cookies.

    python alibaba/discovery.py suggest bluetooth
    python alibaba/discovery.py trending
    python alibaba/discovery.py categories [parent_id]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alibaba import parsers  # noqa: E402
from alibaba.fetch import INSIGHTS, fetch_json, open_service  # noqa: E402
from alibaba.refs import resolve_category_ref  # noqa: E402

SUGGEST_LIMIT = 10
TRENDING_LIMIT = 10
CATEGORY_TREE_MODEL = "10739"
CATEGORY_CHILDREN_MODEL = "10813"


def autocomplete(query, limit=SUGGEST_LIMIT):
    """Search-bar keyword suggestions for a partial query (up to 20), each
    with a ready-to-use search link."""
    if not query:
        raise ValueError("query is required")
    limit = int(limit or SUGGEST_LIMIT)
    if not 1 <= limit <= 20:
        raise ValueError("limit must be 1-20")
    payload = open_service("associationSuggestionViewService", keywords=query, tab="all",
                           bizScene="", pageSize=limit, showAd="false", showGgs="false")
    return parsers.parse_suggestions(payload, query)


def trending_keywords(limit=TRENDING_LIMIT):
    """Trending search queries for the egress country (the gateway picks the
    market from the request IP; there is no country parameter)."""
    limit = int(limit or TRENDING_LIMIT)
    if not 1 <= limit <= 20:
        raise ValueError("limit must be 1-20")
    payload = open_service("popularSuggestionViewService", position="preSearchPanel", pageSize=limit)
    return parsers.parse_trending(payload)


def categories(parent=None):
    """Top-level category tree (grouped as the site's mega-menu shows it), or
    the children of one category when `parent` is given."""
    if parent in (None, ""):
        payload = fetch_json(INSIGHTS, params={"modelId": CATEGORY_TREE_MODEL, "split": "1"})
        return parsers.parse_category_tree(payload)
    parent_id = resolve_category_ref(str(parent))
    payload = fetch_json(INSIGHTS, params={"modelId": CATEGORY_CHILDREN_MODEL, "categoryIds": parent_id})
    return parsers.parse_category_children(payload, parent_id)


if __name__ == "__main__":
    import json
    args = sys.argv[1:] or ["categories"]
    if args[0] == "suggest":
        out = autocomplete(args[1] if len(args) > 1 else "bluetooth")
    elif args[0] == "trending":
        out = trending_keywords()
    else:
        out = categories(args[1] if len(args) > 1 else None)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:4000])
