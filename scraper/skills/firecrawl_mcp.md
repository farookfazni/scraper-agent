## SKILL: Firecrawl MCP (mounted — FIRECRAWL_API_KEY is set)

Firecrawl is a full-featured scraping/crawling API. Five tools:

### firecrawl_scrape
High-quality single-URL scrape — handles JS rendering, anti-bot, and returns
clean markdown. Use as your second choice (after Tavily `extract` if also
mounted) for regular pages, and as the second choice (after `pdf_extract`)
for stubborn PDFs that `pdf_extract` couldn't parse.

### firecrawl_search
Search + scrape combined in one call — searches AND pulls content from top
results. Useful in phase 1 (search) when you want content, not just URLs, in
one round trip.

### firecrawl_crawl
Multi-page crawl — follows links across a site automatically. Use for
"multi-page site crawl" jobs (e.g. "get every product page under /shop") —
this is the primary tool for that scenario; `scrape_urls` is the fallback
only if you already have the exact URL list in hand.

### firecrawl_extract
LLM-guided structured extraction directly from a URL — given a target schema,
it returns matched fields without you having to write CSS selectors. Prefer
this over `extract_structured` (CSS-only, crawl4ai) for `site_type="table"`
pages when the structure is irregular or you don't know the selectors up
front. Use `extract_structured` instead when the table structure is stable
and known — it's faster and doesn't consume extra LLM calls.

### firecrawl_deep_research
Multi-step AI research across many pages — synthesizes findings, not just
raw content. Use for genuinely open-ended research tasks ("what has this
company announced about X in the last year"), not simple single-page lookups
— it's slower and costs more credits than the other four tools.

### Gotchas
- Free tier: 500 credits/month — `firecrawl_deep_research` and
  `firecrawl_crawl` consume more credits per call than `firecrawl_scrape`;
  don't reach for them for simple single-page jobs.
- Needs Node.js 18+ on the host (launched via `npx`).
