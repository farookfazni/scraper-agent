"""
MCP server manager for scraper-agent.

Three optional web-scraping MCP servers — all activate only when the matching
API key is present in the environment. The agent works without any of them
(falls back to Python-client equivalents), but MCP versions are significantly
more capable:

  Tavily MCP    — adds `extract` (direct URL content), not just search
  Firecrawl MCP — adds `crawl`, `deep_research`, `extract` beyond simple scrape
  Apify MCP     — 3,000+ pre-built scrapers for specific sites/platforms

Node.js 18+ is required for Firecrawl and Apify (launched via npx).
"""

from __future__ import annotations

import os
import sys

from agents.mcp import (
    MCPServerStdio,
    MCPServerStreamableHttp,
    MCPServerStreamableHttpParams,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _npx(*args: str, env: dict | None = None) -> dict:
    """Build MCPServerStdio params for an npx-launched server. Windows-safe."""
    if sys.platform == "win32":
        return {
            "command": "cmd",
            "args": ["/c", "npx", *args],
            **({"env": env} if env else {}),
        }
    return {
        "command": "npx",
        "args": list(args),
        **({"env": env} if env else {}),
    }


# ── Builders ─────────────────────────────────────────────────────────────────

def build_tavily_mcp() -> MCPServerStreamableHttp | None:
    """
    Tavily AI Search MCP (StreamableHttp).
    Free tier: 1,000 searches/month — https://app.tavily.com/

    Tools the agent gains:
      search  — web search with snippets and URLs
      extract — pull content directly from one or more URLs (no crawl4ai needed)

    Requires: TAVILY_API_KEY
    """
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return None
    return MCPServerStreamableHttp(
        params=MCPServerStreamableHttpParams(
            url=f"https://mcp.tavily.com/mcp/?tavilyApiKey={api_key}"
        ),
        name="tavily",
        cache_tools_list=True,
        client_session_timeout_seconds=30,
    )


def build_firecrawl_mcp() -> MCPServerStdio | None:
    """
    Firecrawl MCP (stdio via npx).
    Free tier: 500 credits/month — https://www.firecrawl.dev/

    Tools the agent gains:
      firecrawl_scrape         — high-quality single-URL scrape
      firecrawl_search         — search + scrape results in one call
      firecrawl_crawl          — multi-page site crawl (follows links)
      firecrawl_extract        — LLM-guided structured extraction from a URL
      firecrawl_deep_research  — multi-step research across many pages

    Requires: FIRECRAWL_API_KEY + Node.js 18+
    """
    api_key = os.getenv("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        return None
    return MCPServerStdio(
        name="firecrawl",
        params=_npx("-y", "firecrawl-mcp", env={"FIRECRAWL_API_KEY": api_key}),
        cache_tools_list=True,
        client_session_timeout_seconds=30,
    )


def build_apify_mcp() -> MCPServerStdio | None:
    """
    Apify MCP (stdio via npx).
    Free tier: $5/month credits — https://console.apify.com/account/integrations

    Gives the agent access to 3,000+ pre-built scrapers (Apify Actors), e.g.:
      apify/website-content-crawler  — generic site crawler
      apify/cheerio-scraper          — fast lightweight HTML scraper
      apify/social-media-scraper     — Twitter/X, Instagram, LinkedIn
      apify/google-search-scraper    — Google SERP results
      apify/amazon-product-scraper   — Amazon product data
      apify/youtube-scraper          — YouTube video/channel data

    Requires: APIFY_API_KEY + Node.js 18+
    """
    api_key = os.getenv("APIFY_API_KEY", "").strip()
    if not api_key:
        return None
    return MCPServerStdio(
        name="apify",
        params=_npx("-y", "@apify/mcp-server", env={"APIFY_TOKEN": api_key}),
        cache_tools_list=True,
        client_session_timeout_seconds=30,
    )


def build_scraper_mcp_servers() -> list:
    """
    Return all configured MCP servers.
    Servers whose API key is missing are silently omitted — the agent
    gracefully falls back to Python-client tools in that case.
    """
    servers = []
    for builder in (build_tavily_mcp, build_firecrawl_mcp, build_apify_mcp):
        srv = builder()
        if srv is not None:
            servers.append(srv)
    return servers
