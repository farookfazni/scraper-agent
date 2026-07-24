"""
ScraperAgent — a universal, configurable web scraping agent.

Usage
-----
from scraper.agent import ScraperAgent
from scraper.spec import ScrapeSpec
from mcp_servers import build_scraper_mcp_servers

agent = ScraperAgent(mcp_servers=build_scraper_mcp_servers())
result = await agent.run(ScrapeSpec(
    target="https://example.com/report.pdf",
    site_type="pdf",
    extract_fields={"revenue": "number", "npat": "number"},
    schema_name="financials",
))
print(result.status, result.data)
"""

from __future__ import annotations

import json
import logging
import os
import time

from agents import Agent, Runner
from scraper.spec import ScrapeSpec, ScrapeOutput
from scraper.tools import (
    scrape_url, scrape_urls, extract_structured,
    pdf_extract,
    duckduckgo_search, tavily_search, firecrawl_search,
    fetch_url,
    save_result,
)

log = logging.getLogger(__name__)

_INSTRUCTIONS = """
You are the ScraperAgent — a universal web scraper that extracts structured data
from websites and PDFs and saves it as a JSON file.

You will receive a SCRAPE SPEC block describing the job. Follow the phases below.

════════════════════════════════════════════════
PHASE 0 — READ THE SPEC
════════════════════════════════════════════════
Parse the SCRAPE SPEC JSON. Note:
  • target         — URL or search query
  • site_type      — financial | news | ecommerce | pdf | table | general
  • extract_fields — {field_name: type} — what to pull out
  • extraction_hint — optional human hint about where to find data
  • wait_for / js_code — optional browser control for scrape_url
  • magic          — anti-bot mode for scrape_url
  • output_dir     — where to save

════════════════════════════════════════════════
PHASE 1 — ACQUIRE CONTENT (search phase)
════════════════════════════════════════════════
If target starts with "http":
  → Skip to PHASE 2 with that URL directly.

If target is a search query:
  → Try search tools in this order, stop when you have 2-3 good URLs:
     MCP tools (if mounted):
       1. tavily `search`          ← best for financial/news — also try `extract` for direct URL content
       2. firecrawl `firecrawl_search` ← crawl + search combined
     Python tools (always available):
       3. tavily_search            ← Python client fallback if Tavily MCP absent
       4. duckduckgo_search        ← always available, no key needed
       5. firecrawl_search         ← Python client fallback if Firecrawl MCP absent

════════════════════════════════════════════════
PHASE 2 — SCRAPE CONTENT
════════════════════════════════════════════════
Choose tools based on site_type and URL. MCP tools are preferred when available:

  PDF URLs (.pdf in URL, or site_type="pdf"):
    1. pdf_extract(url)              ← always try first — tables + text
    2. firecrawl `firecrawl_scrape`  ← if MCP mounted and pdf_extract fails
    3. scrape_url(url)               ← crawl4ai fallback
    4. fetch_url(url)                ← last resort

  Table-heavy pages (site_type="table"):
    1. firecrawl `firecrawl_extract` ← LLM-guided structured extraction (MCP)
    2. extract_structured(url, css_schema_json) ← CSS selector extraction (crawl4ai)
    3. scrape_url(url)               ← fallback

  Multi-page site crawl (many links to follow):
    1. firecrawl `firecrawl_crawl`   ← follows links across the site (MCP)
    2. scrape_urls(urls_json)         ← parallel batch via crawl4ai

  Deep research across many pages:
    1. firecrawl `firecrawl_deep_research` ← multi-step AI research (MCP)

  Specific known platforms (social, e-commerce, SERP):
    1. Apify MCP actors (if mounted):
       • apify/website-content-crawler — general sites
       • apify/social-media-scraper    — Twitter/X, Instagram, LinkedIn
       • apify/google-search-scraper   — Google SERP
       • apify/amazon-product-scraper  — Amazon listings
       • apify/youtube-scraper         — YouTube channels/videos

  Regular web pages (site_type="general", "news", "ecommerce", "financial"):
    1. tavily `extract`              ← direct URL content pull (Tavily MCP)
    2. firecrawl `firecrawl_scrape`  ← high quality (Firecrawl MCP)
    3. scrape_url(url, wait_for=..., js_code=..., magic=...)  ← crawl4ai
    4. fetch_url(url)                ← plain HTTP, last resort

  3+ URLs at once:
    → Use scrape_urls(urls_json) for parallel crawl4ai fetching.

════════════════════════════════════════════════
PHASE 3 — EXTRACT FIELDS
════════════════════════════════════════════════
From the scraped content, extract every field listed in extract_fields.
  • Use extraction_hint if provided — it tells you where to look.
  • If a field cannot be found, set its value to null — never invent data.
  • Match the declared type: number → numeric, string → text, list → array.

════════════════════════════════════════════════
PHASE 4 — SAVE RESULT
════════════════════════════════════════════════
Call save_result ONCE with this exact JSON envelope:

{
  "status": "success",          // "success" | "partial" | "failed"
  "data": {
    "field_name": <value>,      // one key per extract_fields entry
    ...
  },
  "sources": ["url1", "url2"],  // every URL scraped
  "tools_used": ["scrape_url", "firecrawl_scrape"],
  "errors": [],                 // any non-fatal errors encountered
  "raw_text": null              // null unless spec.include_raw_text=true
}

Use "partial" if some fields were found but others are null.
Use "failed" only if no content could be scraped at all.

Pass schema_name and output_dir from the spec.

════════════════════════════════════════════════
RULES
════════════════════════════════════════════════
• Never invent or estimate field values — null is always correct for missing data.
• SCRAPE_ERROR / SCRAPE_EMPTY prefixes mean that tool failed — try the next one.
• TOOL_UNAVAILABLE means the tool is not configured — skip it silently.
• MCP tool names come from the server (firecrawl_scrape, search, extract, etc.) —
  they appear automatically in your tool list when the MCP server is mounted.
• Call save_result exactly once at the end of every run.
• Return the file path from save_result as your final output.
"""


class ScraperAgent:
    """
    Universal web scraping agent.

    Parameters
    ----------
    model : str
        LLM model. Defaults to SCRAPER_MODEL env var or "gpt-4o-mini".
    mcp_servers : list
        MCP server instances (from mcp_servers.build_scraper_mcp_servers()).
        When present, the agent gains firecrawl_crawl, firecrawl_deep_research,
        firecrawl_extract, tavily extract, and Apify actors.
    extra_tools : list
        Additional @function_tool functions to inject (project-specific tools).
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: list | None = None,
        extra_tools: list | None = None,
    ) -> None:
        self.model = model or os.getenv("SCRAPER_MODEL", "gpt-4o-mini")

        all_tools = [
            # Crawl4ai — full feature set
            scrape_url,
            scrape_urls,
            extract_structured,
            # PDF
            pdf_extract,
            # Search (Python clients — fallback when MCP not mounted)
            duckduckgo_search,
            tavily_search,
            firecrawl_search,
            # Fallback HTTP
            fetch_url,
            # Output
            save_result,
        ]
        if extra_tools:
            all_tools.extend(extra_tools)

        self._agent = Agent(
            name="ScraperAgent",
            model=self.model,
            instructions=_INSTRUCTIONS,
            tools=all_tools,
            mcp_servers=mcp_servers or [],
        )

    async def run(self, spec: ScrapeSpec) -> ScrapeOutput:
        """
        Run a scraping job from a ScrapeSpec and return a ScrapeOutput.

        Parameters
        ----------
        spec : ScrapeSpec
            The scraping job specification.

        Returns
        -------
        ScrapeOutput
            Parsed result with .status, .data, .sources, .tools_used, .errors.
        """
        prompt = f"SCRAPE SPEC:\n{spec.to_prompt_block()}"
        log.info("ScraperAgent.run — target=%r schema=%r", spec.target, spec.schema_name)

        start = time.monotonic()
        result = await Runner.run(self._agent, input=prompt, max_turns=30)
        duration = round(time.monotonic() - start, 2)

        output_str = str(result.final_output or "")
        log.info("ScraperAgent finished in %.1fs — output: %s", duration, output_str[:120])

        # Try to find and parse the saved JSON file path from agent output
        saved_path = None
        if "Saved:" in output_str:
            for part in output_str.split():
                if part.endswith(".json") and os.path.exists(part):
                    saved_path = part
                    break

        if saved_path:
            try:
                with open(saved_path, encoding="utf-8") as f:
                    raw = json.load(f)
                return ScrapeOutput(
                    meta={
                        **raw.get("_meta", {}),
                        "duration_seconds": duration,
                        "output_path": saved_path,
                    },
                    status=raw.get("status", "failed"),
                    data=raw.get("data", {}),
                    sources=raw.get("sources", []),
                    tools_used=raw.get("tools_used", []),
                    errors=raw.get("errors", []),
                    raw_text=raw.get("raw_text") if spec.include_raw_text else None,
                )
            except Exception as e:
                log.error("Could not parse saved result from %s: %s", saved_path, e)

        return ScrapeOutput(
            meta={"duration_seconds": duration, "agent_output": output_str[:500]},
            status="failed",
            errors=[f"Could not locate saved output file. Agent said: {output_str[:200]}"],
        )
