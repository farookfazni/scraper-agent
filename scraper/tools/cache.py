"""
In-process memoization for scraper tools.
Keyed by MD5(fn_name + args) — transparent to the agent.
Cleared by calling clear_cache() or on process exit.
"""

from __future__ import annotations

import functools
import hashlib
import json
from typing import Any, Callable

_CACHE: dict[str, Any] = {}


def _make_key(fn_name: str, args: tuple, kwargs: dict) -> str:
    payload = json.dumps({"fn": fn_name, "args": args, "kwargs": kwargs},
                         sort_keys=True, default=str)
    return hashlib.md5(payload.encode()).hexdigest()


def cached_tool(fn: Callable) -> Callable:
    """
    Decorator that caches the return value of a tool function.
    Works for both sync and async functions.
    """
    import asyncio

    if asyncio.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            key = _make_key(fn.__name__, args, kwargs)
            if key in _CACHE:
                return _CACHE[key]
            result = await fn(*args, **kwargs)
            _CACHE[key] = result
            return result
        return async_wrapper
    else:
        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            key = _make_key(fn.__name__, args, kwargs)
            if key in _CACHE:
                return _CACHE[key]
            result = fn(*args, **kwargs)
            _CACHE[key] = result
            return result
        return sync_wrapper


def clear_cache() -> int:
    """Clear all cached results. Returns number of entries removed."""
    count = len(_CACHE)
    _CACHE.clear()
    return count
