"""Bottle handler plumbing shared by every route: validate the query with a
marshmallow schema, run the endpoint function (optionally through the cache),
map the failure taxonomy to HTTP, and add gateway-style pagination links
(count / per_page / current_page / total_pages / next / previous) built from
the caller's own query params.
"""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from cache import cached_call
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from schema_fields import load_query


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The request query as a plain dict of unicode strings (bottle 0.12's
    .get() hands back latin-1 decoded bytes, so getunicode is mandatory)."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def public_base():
    """scheme://host for pagination links: a reverse proxy's X-Forwarded-Host
    (https) if present, otherwise the host this request came in on."""
    fwd = (request.headers.get("X-Forwarded-Host") or "").split(",")[0].strip()
    if fwd:
        return f"https://{fwd.split(':')[0]}"
    parts = request.urlparts
    return f"{parts.scheme}://{parts.netloc}"


def _page_link(base, path, params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "", False)}
    query["page"] = page
    return f"{base}{path}?{urlencode(query, doseq=True)}"


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def paginate(result, path, raw_params, base):
    """Lift the scraper's `pagination` block ({page, items_per_page,
    total_pages, total_count}) into the flat shape with next/previous links."""
    pagination = result.pop("pagination", None) or {}
    result.pop("count", None)   # per-page count; `count` is the total
    page = _as_int(pagination.get("page")) or _as_int(raw_params.get("page")) or 1
    total_pages = max(_as_int(pagination.get("total_pages")), 0)
    params = dict(raw_params)
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(base, path, params, page + 1 if page < total_pages else None),
        "previous": _page_link(base, path, params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def route_call(schema_cls, impl, *, site, path, paginated=False, cache_ttl=None):
    """One handler body: ValidationError / ValueError / BadRequest -> 400,
    NotFound -> 404, Blocked / UpstreamError -> 502, anything else -> 500."""
    label = f"{site} {path.strip('/').replace(site + '/', '', 1)}"
    raw = query_dict()
    data, error = load_query(schema_cls, raw)
    if error:
        return json_response(error, 400)
    try:
        if cache_ttl:
            result = cached_call(f"{site}.{impl.__name__}", data, impl, cache_ttl)
        else:
            result = impl(**data)
    except ValueError as e:
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:
        return json_response({"error": f"{site} rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Blocked as e:
        return json_response({"error": f"{site} blocked the request, retry later: {e}"}, 502)
    except UpstreamError as e:
        return json_response({"error": f"{label} failed: {e}"}, 502)
    except Exception as e:
        return json_response({"error": f"{label} failed: {type(e).__name__}: {e}"}, 500)
    if paginated:
        result = paginate(result, path, raw, public_base())
    return json_response(result)


def route_table(site):
    """A register(path, schema, impl, paginated=False, cache=None) function
    that mounts a GET route through route_call."""
    def register(path, schema, impl, paginated=False, cache=None):
        def handler():
            return route_call(schema, impl, site=site, path=path, paginated=paginated, cache_ttl=cache)
        handler.__name__ = f"{site}_" + path.strip("/").replace("/", "_").replace("-", "_")
        route(path, method="GET")(handler)
        return handler
    return register
