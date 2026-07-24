"""
fetch_url — plain HTTP GET, last-resort fallback.
No JavaScript rendering, no browser — just raw HTML text.
"""

from __future__ import annotations

import logging

from agents import function_tool
from scraper.tools.cache import cached_tool

log = logging.getLogger(__name__)


@function_tool
@cached_tool
def fetch_url(url: str) -> str:
    """
    Fetch the text content of a URL via plain HTTP GET.
    Use this ONLY as a last resort — it cannot render JavaScript.
    Returns up to 15 000 characters of text content.

    Args:
        url: Full URL to fetch (https://...).

    Returns:
        Raw HTML/text content, or a SCRAPE_ERROR string.
    """
    try:
        import httpx
    except ImportError:
        return "TOOL_UNAVAILABLE: httpx not installed — pip install httpx"

    log.info("fetch_url: %s", url)
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ScraperAgent/1.0)"}
        with httpx.Client(timeout=15.0, follow_redirects=True, verify=False) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if any(t in content_type for t in ("pdf", "octet-stream", "zip", "binary")):
            return (
                f"SCRAPE_ERROR: fetch_url — binary content ({content_type}). "
                "Use pdf_extract for PDFs."
            )

        text = resp.text[:15_000]
        log.info("fetch_url: %s — %d chars", url, len(text))
        return text

    except Exception as e:
        log.warning("fetch_url failed for %s: %s", url, e)
        return f"SCRAPE_ERROR: fetch_url — {e}"
