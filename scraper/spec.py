"""
ScrapeSpec  — what to scrape and what to extract.
ScrapeOutput — the fixed output envelope every job produces.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field


class ScrapeSpec(BaseModel):
    """
    Describes a single scraping job. Pass one to ScraperAgent.run().

    Examples
    --------
    # Scrape a known URL for structured fields
    ScrapeSpec(
        target="https://example.com/annual-report-2024.pdf",
        site_type="pdf",
        extract_fields={"revenue": "number", "npat": "number", "eps": "number"},
        schema_name="annual_report",
    )

    # Search then scrape
    ScrapeSpec(
        target="JKH annual report 2024 site:cse.lk",
        site_type="financial",
        extract_fields={"company": "string", "year": "integer", "revenue_mn": "number"},
        schema_name="cse_financials",
        max_search_results=3,
    )
    """

    # ── What to scrape ────────────────────────────────────────────────────────
    target: str = Field(
        ...,
        description="A direct URL (https://...) or a plain-text search query.",
    )
    site_type: Literal["financial", "news", "ecommerce", "pdf", "table", "general"] = Field(
        "general",
        description=(
            "Hint used to choose the best tool and extraction strategy.\n"
            "  financial  — annual reports, balance sheets, financial statements\n"
            "  news       — articles, press releases\n"
            "  ecommerce  — product pages, pricing\n"
            "  pdf        — force PDF extraction even if URL doesn't end in .pdf\n"
            "  table      — pages with tabular data (uses CSS/JSON extraction)\n"
            "  general    — no hint given; the agent should classify the actual\n"
            "               content itself (from the URL/domain and what it scrapes)\n"
            "               and follow whichever row above actually fits, rather than\n"
            "               assuming 'general' is accurate just because it's the default."
        ),
    )

    # ── What to extract ───────────────────────────────────────────────────────
    extract_fields: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Fields to extract. Key = output field name, value = type hint.\n"
            "  Supported types: string, number, integer, boolean, list, object\n"
            "  Example: {\"company\": \"string\", \"revenue\": \"number\", \"years\": \"list\"}\n"
            "  Leave empty ({}) to let the agent decide what's worth extracting —\n"
            "  it will derive fields from extraction_hint if given, or otherwise\n"
            "  produce a general-purpose summary (title, summary, key_points, and\n"
            "  any obviously structured data it finds on the page)."
        ),
    )
    schema_name: str = Field(
        "scraped",
        description="Short label used to name the output JSON file.",
    )
    extraction_hint: str | None = Field(
        None,
        description=(
            "Optional free-text instruction from the user about what they want —\n"
            "this doubles as the primary user-facing input when extract_fields is\n"
            "empty (e.g. 'get me the pricing tiers', 'summarize the main topics').\n"
            "Use it to decide what fields to extract, not just where to find them.\n"
            "Example: 'Revenue is in the Consolidated Statement of Profit or Loss table.'"
        ),
    )

    # ── Browser / JS control ─────────────────────────────────────────────────
    wait_for: str | None = Field(
        None,
        description=(
            "CSS selector OR JS expression to wait for before extracting.\n"
            "Use for React/Vue pages that render content after page load.\n"
            "Example: 'table.financial-data' or 'js:document.querySelector(\".data\")'"
        ),
    )
    js_code: str | None = Field(
        None,
        description=(
            "JavaScript to execute on the page before scraping.\n"
            "Use to click buttons, expand sections, or trigger lazy-loading.\n"
            "Example: 'document.querySelector(\".load-more\").click();'"
        ),
    )
    use_session: bool = Field(
        False,
        description=(
            "Reuse a persistent browser session (for login flows or multi-page scraping). "
            "This is a job-level hint only — scrape_url's own session_id parameter takes an "
            "arbitrary STRING (not this boolean). If this is true, invent a session_id string "
            "and pass the same one on every scrape_url call for this job."
        ),
    )
    magic: bool = Field(
        False,
        description="Enable crawl4ai magic mode — automatic anti-bot bypass.",
    )
    respect_robots_txt: bool = Field(
        False,
        description="Honor the site's robots.txt before scraping with scrape_url.",
    )
    remove_popups: bool = Field(
        False,
        description="Strip cookie/consent banners and overlay modals before extracting content.",
    )
    css_selector: str | None = Field(
        None,
        description=(
            "CSS selector to scope extraction to a specific container "
            "(e.g. 'main.report-content'). Useful for table/financial pages "
            "with a lot of surrounding nav/ad noise."
        ),
    )
    excluded_tags: str | None = Field(
        None,
        description="Comma-separated HTML tags to drop entirely, e.g. 'nav,footer,aside'.",
    )
    exclude_external_links: bool = Field(
        False,
        description="Drop links pointing outside the scraped domain from the extracted markdown.",
    )
    scan_full_page: bool = Field(
        False,
        description="Auto-scroll the page before extracting — use for infinite-scroll feeds.",
    )

    # ── Search settings (only when target is a query) ────────────────────────
    max_search_results: int = Field(
        3,
        description="Max URLs to collect from search before moving to scrape phase.",
        ge=1,
        le=10,
    )

    # ── Output ────────────────────────────────────────────────────────────────
    output_dir: str = Field(
        "output",
        description="Directory where the output JSON file is written (relative to CWD).",
    )
    include_raw_text: bool = Field(
        False,
        description="Include the full scraped text in the output file (useful for debugging).",
    )

    def to_prompt_block(self) -> str:
        """Serialize to the JSON block injected into the agent prompt."""
        return json.dumps(self.model_dump(), indent=2, default=str)


class ScrapeOutput(BaseModel):
    """Fixed JSON envelope returned by every scraping job."""

    # ── Metadata ──────────────────────────────────────────────────────────────
    meta: dict[str, Any] = Field(
        default_factory=dict,
        description="source_url, tool_used, scraped_at, duration_seconds, schema_name",
    )

    # ── Result ────────────────────────────────────────────────────────────────
    status: Literal["success", "partial", "failed"] = "failed"
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted fields as specified in ScrapeSpec.extract_fields.",
    )

    # ── Diagnostics ───────────────────────────────────────────────────────────
    sources: list[str] = Field(
        default_factory=list,
        description="All URLs that were scraped to produce this output.",
    )
    tools_used: list[str] = Field(
        default_factory=list,
        description="Scraping tools that were called (in order).",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Errors encountered during the run (non-fatal ones included).",
    )
    raw_text: str | None = Field(
        None,
        description="Full scraped text — only included if ScrapeSpec.include_raw_text=True.",
    )
