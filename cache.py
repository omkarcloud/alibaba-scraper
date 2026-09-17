"""Optional in-memory response cache (ALIBABA_CACHE=1).

    result = cached_call("alibaba.product_details", data, impl, ttl=timedelta(days=1))

`data` is the endpoint's validated kwargs dict, so `?page=1` and no `page`
share one entry. Off by default so every call returns live data; turn it on
when you hammer the same products/searches and want instant repeats. Entries
expire per alibaba/cache_config.py and the store is bounded to MAX_ENTRIES.
"""
import json
import threading
import time
from copy import deepcopy
from hashlib import sha256

import config

MAX_ENTRIES = 5000
_store = {}
_lock = threading.Lock()


class DontCache:
    """Wrap a result to return it without storing it."""

    def __init__(self, data):
        self.data = data


def _key(namespace, data):
    return sha256((namespace + json.dumps(data, sort_keys=True, default=str)).encode()).hexdigest()


def cached_call(namespace, data, fn, ttl, cache=True):
    if not (config.CACHE_ENABLED and cache and ttl):
        result = fn(**data)
        return result.data if isinstance(result, DontCache) else result
    key = _key(namespace, data)
    now = time.time()
    with _lock:
        hit = _store.get(key)
        if hit and hit[0] > now:
            return deepcopy(hit[1])
    result = fn(**data)
    if isinstance(result, DontCache):
        return result.data
    with _lock:
        if len(_store) >= MAX_ENTRIES:
            for k in [k for k, (exp, _) in _store.items() if exp <= now]:
                del _store[k]
            while len(_store) >= MAX_ENTRIES:
                del _store[next(iter(_store))]
        _store[key] = (now + ttl.total_seconds(), deepcopy(result))
    return result


def clear():
    with _lock:
        _store.clear()
