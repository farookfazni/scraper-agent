## SKILL: Tavily MCP (mounted — TAVILY_API_KEY is set)

Tavily is a search-and-extract API purpose-built for AI agents. Two tools are
confirmed stable and documented:

### search
Real-time web search with snippets and URLs. Best search tool for
`site_type="financial"`/`"news"` queries — Tavily is tuned for current-events
and finance-adjacent content. Prefer this over `duckduckgo_search` whenever
it's available.

### extract
Pulls clean content directly from one or more URLs — no crawl4ai/browser
needed. Use this FIRST for `site_type="general"/"news"/"ecommerce"/"financial"`
pages before falling back to `firecrawl_scrape` or `scrape_url`. Handles
JS-rendered pages server-side.

### Possibly also available: map / crawl
Your actual mounted tool list may also include `map` (site structure mapping)
and `crawl` (systematic multi-page crawl) — Tavily has been expanding this
server's tool set and documentation sources disagree on the current count.
**Check your own available tool list rather than assuming** — if `crawl` is
present, it's an alternative to `firecrawl_crawl` for multi-page jobs; use
whichever MCP server you have, no strong preference between them.

### Gotchas
- Free tier: 1,000 searches/month.
- If `search`/`extract` return no useful results, don't loop — fall back to
  `duckduckgo_search` or `firecrawl_search` per the phase 1 search order.
