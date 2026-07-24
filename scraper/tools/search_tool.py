"""
Search tools — find URLs before scraping.

Priority:
  1. Tavily (TAVILY_API_KEY)  — best for financial / news content
  2. DuckDuckGo              — always available, no key
  3. Firecrawl search (FIRECRAWL_API_KEY) — fallback
"""

from __future__ import annotations

import json
import logging
import os

from agents import function_tool

log = logging.getLogger(__name__)


@function_tool
async def tavily_search(query: str, max_results: int = 5) -> str:
    """
    Search the web using Tavily — best for financial news, annual reports, IR pages.
    Requires TAVILY_API_KEY in environment.

    Args:
        query:       Search query string.
        max_results: Maximum number of results to return (1–10).

    Returns:
        JSON array of {url, title, snippet} objects, or TOOL_UNAVAILABLE.
    """
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return "TOOL_UNAVAILABLE: TAVILY_API_KEY not set"

    try:
        from tavily import TavilyClient
    except ImportError:
        return "TOOL_UNAVAILABLE: tavily-python not installed — pip install tavily-python"

    try:
        log.info("tavily_search: %r (max %d)", query, max_results)
        client = TavilyClient(api_key=api_key)
        resp = client.search(query, max_results=max_results, search_depth="advanced")
        results = [
            {"url": r.get("url"), "title": r.get("title", ""), "snippet": r.get("content", "")[:300]}
            for r in resp.get("results", [])
        ]
        log.info("tavily_search: %d results", len(results))
        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        log.warning("tavily_search failed: %s", e)
        return f"SEARCH_ERROR: Tavily — {e}"


@function_tool
def duckduckgo_search(query: str, max_results: int = 5) -> str:
    """
    Search the web using DuckDuckGo — always available, no API key needed.

    Args:
        query:       Search query string.
        max_results: Maximum number of results to return (1–10).

    Returns:
        JSON array of {url, title, snippet} objects, or SEARCH_ERROR.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        return "TOOL_UNAVAILABLE: ddgs not installed — pip install ddgs"

    try:
        log.info("duckduckgo_search: %r (max %d)", query, max_results)
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "url":     r.get("href") or r.get("url", ""),
                    "title":   r.get("title", ""),
                    "snippet": r.get("body", "")[:300],
                })
        log.info("duckduckgo_search: %d results", len(results))
        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        log.warning("duckduckgo_search failed: %s", e)
        return f"SEARCH_ERROR: DuckDuckGo — {e}"


@function_tool
def firecrawl_search(query: str, max_results: int = 5) -> str:
    """
    Search using Firecrawl — fallback when Tavily and DuckDuckGo are insufficient.
    Requires FIRECRAWL_API_KEY in environment.

    Args:
        query:       Search query string.
        max_results: Maximum number of results to return.

    Returns:
        JSON array of {url, title, snippet} objects, or TOOL_UNAVAILABLE.
    """
    api_key = os.getenv("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        return "TOOL_UNAVAILABLE: FIRECRAWL_API_KEY not set"

    try:
        from firecrawl import FirecrawlApp
    except ImportError:
        return "TOOL_UNAVAILABLE: firecrawl-py not installed — pip install firecrawl-py"

    try:
        log.info("firecrawl_search: %r (max %d)", query, max_results)
        app = FirecrawlApp(api_key=api_key)
        resp = app.search(query, limit=max_results)

        if isinstance(resp, dict):
            items = resp.get("data", resp.get("results", []))
        elif isinstance(resp, list):
            items = resp
        else:
            items = []

        results = [
            {"url": r.get("url", ""), "title": r.get("title", ""), "snippet": r.get("description", "")[:300]}
            for r in items
        ]
        log.info("firecrawl_search: %d results", len(results))
        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        log.warning("firecrawl_search failed: %s", e)
        return f"SEARCH_ERROR: Firecrawl — {e}"
