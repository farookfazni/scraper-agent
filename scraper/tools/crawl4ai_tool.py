"""
crawl4ai scraping tools — full feature set.

Four tools exported:
  scrape_url        — single URL, full options (wait_for, js_code, session, magic)
  scrape_urls       — parallel scrape of multiple URLs via arun_many
  extract_structured — CSS/JSON schema extraction (no LLM, fast, for table-heavy pages)
  scrape_pdf_url    — crawl4ai PDF extraction (fallback when pdfplumber fails)
"""

from __future__ import annotations

import json
import logging

from agents import function_tool
from scraper.tools.cache import cached_tool

log = logging.getLogger(__name__)


def _import_crawl4ai():
    try:
        import crawl4ai
        return crawl4ai
    except ImportError:
        return None


@function_tool
@cached_tool
async def scrape_url(
    url: str,
    wait_for: str = "",
    js_code: str = "",
    use_session: str = "",
    magic: bool = False,
    word_count_threshold: int = 50,
) -> str:
    """
    Scrape a single URL using crawl4ai with full browser control.

    Args:
        url:                  Full URL to scrape (https://...).
        wait_for:             CSS selector or JS expression to wait for before extracting.
                              Example: 'table.results' or 'js:window.__data !== undefined'
        js_code:              JavaScript to run on the page before extracting.
                              Example: 'document.querySelector(".expand").click();'
        use_session:          Session ID string to reuse a browser session across calls.
                              Pass the same string on subsequent calls to share state.
                              Leave empty to use a fresh session each time.
        magic:                Enable crawl4ai anti-bot bypass mode.
        word_count_threshold: Minimum words a content block must have to be kept.

    Returns:
        Clean markdown text with source header, or a SCRAPE_ERROR/SCRAPE_EMPTY string.
    """
    c4 = _import_crawl4ai()
    if c4 is None:
        return "TOOL_UNAVAILABLE: crawl4ai not installed — pip install crawl4ai"

    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

        browser_cfg = BrowserConfig(headless=True, verbose=False)
        run_cfg = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            word_count_threshold=word_count_threshold,
            wait_for=wait_for or None,
            js_code=js_code or None,
            session_id=use_session or None,
            magic=magic,
            page_timeout=30_000,
            simulate_user=magic,
            override_navigator=magic,
        )

        log.info("crawl4ai scraping %s (wait_for=%r, js=%r, magic=%s)", url, wait_for or None, bool(js_code), magic)

        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            result = await crawler.arun(url=url, config=run_cfg)

        if not result.success:
            err = getattr(result, "error_message", "unknown error")
            log.warning("crawl4ai failed for %s: %s", url, err)
            return f"SCRAPE_ERROR: crawl4ai — {err}"

        # fit_markdown is the cleaned version (links stripped, noise removed)
        # fall back to raw_markdown, then extracted_content
        md = getattr(result, "markdown", None)
        if md and hasattr(md, "fit_markdown") and md.fit_markdown:
            content = md.fit_markdown
        elif md and hasattr(md, "raw_markdown") and md.raw_markdown:
            content = md.raw_markdown
        elif md and isinstance(md, str):
            content = md
        else:
            content = getattr(result, "extracted_content", "") or ""

        content = str(content).strip()
        if not content:
            return "SCRAPE_EMPTY: crawl4ai extracted no text from this page"

        if len(content) > 20_000:
            content = content[:20_000] + "\n\n[... truncated at 20 000 chars ...]"

        log.info("crawl4ai scraped %s — %d chars", url, len(content))
        return f"[Source: {url}]\n\n{content}"

    except Exception as e:
        log.warning("crawl4ai exception for %s: %s", url, e)
        return f"SCRAPE_ERROR: crawl4ai — {e}"


@function_tool
async def scrape_urls(urls_json: str) -> str:
    """
    Scrape multiple URLs in parallel using crawl4ai's arun_many.
    Significantly faster than calling scrape_url one at a time.

    Args:
        urls_json: JSON array of URL strings.
                   Example: ["https://a.com", "https://b.com", "https://c.com"]

    Returns:
        JSON array — one object per URL with keys: url, status, content.
    """
    c4 = _import_crawl4ai()
    if c4 is None:
        return "TOOL_UNAVAILABLE: crawl4ai not installed — pip install crawl4ai"

    try:
        urls = json.loads(urls_json)
        if not isinstance(urls, list) or not urls:
            return "ERROR: urls_json must be a non-empty JSON array of strings"
    except json.JSONDecodeError as e:
        return f"ERROR: invalid JSON — {e}"

    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

        browser_cfg = BrowserConfig(headless=True, verbose=False)
        run_cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=30_000)

        log.info("crawl4ai parallel scraping %d URLs", len(urls))

        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            results = await crawler.arun_many(urls=urls, config=run_cfg)

        output = []
        for res in results:
            url = getattr(res, "url", "unknown")
            if not res.success:
                err = getattr(res, "error_message", "failed")
                log.warning("crawl4ai parallel: %s failed — %s", url, err)
                output.append({"url": url, "status": "error", "content": f"SCRAPE_ERROR: {err}"})
                continue

            md = getattr(res, "markdown", None)
            if md and hasattr(md, "fit_markdown") and md.fit_markdown:
                content = md.fit_markdown
            elif md and hasattr(md, "raw_markdown") and md.raw_markdown:
                content = md.raw_markdown
            elif md and isinstance(md, str):
                content = md
            else:
                content = getattr(res, "extracted_content", "") or ""

            content = str(content).strip()
            if len(content) > 15_000:
                content = content[:15_000] + "\n\n[... truncated ...]"

            output.append({"url": url, "status": "ok", "content": content})
            log.info("crawl4ai parallel: %s — %d chars", url, len(content))

        return json.dumps(output, ensure_ascii=False)

    except Exception as e:
        log.warning("crawl4ai arun_many failed: %s", e)
        return f"SCRAPE_ERROR: crawl4ai parallel — {e}"


@function_tool
@cached_tool
async def extract_structured(url: str, css_schema_json: str) -> str:
    """
    Extract structured data from a page using CSS selectors — no LLM needed.
    Best for table-heavy pages where you know the HTML structure.

    Args:
        url:             URL of the page to scrape.
        css_schema_json: JSON object defining the extraction schema.
                         Schema format:
                         {
                           "name": "schema_name",
                           "baseSelector": "table.data tr",
                           "fields": [
                             {"name": "year",    "selector": "td:nth-child(1)", "type": "text"},
                             {"name": "revenue", "selector": "td:nth-child(2)", "type": "text"}
                           ]
                         }

    Returns:
        JSON array of extracted objects, one per matched baseSelector element.
    """
    c4 = _import_crawl4ai()
    if c4 is None:
        return "TOOL_UNAVAILABLE: crawl4ai not installed — pip install crawl4ai"

    try:
        schema = json.loads(css_schema_json)
    except json.JSONDecodeError as e:
        return f"ERROR: invalid css_schema_json — {e}"

    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
        from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

        strategy = JsonCssExtractionStrategy(schema, verbose=False)
        browser_cfg = BrowserConfig(headless=True, verbose=False)
        run_cfg = CrawlerRunConfig(
            extraction_strategy=strategy,
            cache_mode=CacheMode.BYPASS,
            page_timeout=30_000,
        )

        log.info("crawl4ai CSS extraction from %s", url)

        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            result = await crawler.arun(url=url, config=run_cfg)

        if not result.success:
            return f"SCRAPE_ERROR: crawl4ai CSS extraction — {result.error_message}"

        extracted = result.extracted_content
        if not extracted:
            return "SCRAPE_EMPTY: CSS extraction found no matching elements"

        log.info("crawl4ai CSS extraction from %s — got %d chars", url, len(str(extracted)))
        return extracted if isinstance(extracted, str) else json.dumps(extracted, ensure_ascii=False)

    except Exception as e:
        log.warning("crawl4ai CSS extraction failed for %s: %s", url, e)
        return f"SCRAPE_ERROR: crawl4ai CSS extraction — {e}"
