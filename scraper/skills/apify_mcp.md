## SKILL: Apify MCP (mounted — APIFY_API_KEY is set)

IMPORTANT: unlike Tavily/Firecrawl, Apify does NOT give you one fixed tool
per scraper. It exposes generic tools for *discovering and running* any of
the 3,000+ pre-built scrapers ("Actors") in the Apify Store. The workflow is
always: search → inspect → call → fetch results.

### Core workflow tools
1. **search-actors** — search the Apify Store by keyword (e.g.
   `"amazon product scraper"`, `"instagram profile"`, `"google maps"`).
   Returns candidate Actors with IDs.
2. **fetch-actor-details** — given an Actor ID, get its expected JSON input
   schema. ALWAYS do this before calling an Actor you haven't used before —
   guessing the input shape will fail.
3. **call-actor** — run an Actor with the input from step 2, get the run
   results back (or a run ID for a long job).
4. **get-dataset-items** — pull paginated results from a finished run's
   dataset (use if call-actor returns a dataset reference rather than inline
   results).

### Supporting tools
`get-actor-run` / `get-actor-run-list` / `get-actor-log` — inspect a run's
status/history/logs, useful if a call-actor run is slow or you need to debug
a failure. `get-dataset` / `get-dataset-schema` / `get-dataset-list` —
dataset metadata. `get-key-value-store*` — for Actors that store results as
key-value records instead of a dataset. `search-apify-docs` /
`fetch-apify-docs` — look up Apify's own documentation if an Actor's input
schema is unclear.

### When to reach for Apify instead of crawl4ai/Firecrawl
Use Apify when the target is a *known platform* with quirks generic scrapers
struggle with (login walls, infinite scroll, anti-bot, platform-specific
pagination) — search-actors for one of these categories first:

| Category | Example search terms |
|---|---|
| E-commerce | "amazon product scraper", "ebay scraper", "shopify scraper" |
| Social media | "instagram scraper", "tiktok scraper", "twitter/x scraper", "linkedin scraper" |
| Search engines / SERP | "google search scraper", "bing search scraper" |
| Maps / POI | "google maps scraper", "google places scraper" |
| Jobs | "linkedin jobs scraper", "indeed scraper" |
| Real estate | "zillow scraper", "real estate listings scraper" |
| Reviews | "google reviews scraper", "trustpilot scraper", "yelp scraper" |
| Video | "youtube scraper", "youtube channel scraper" |
| General site crawl | "website content crawler" |

Don't hardcode an Actor ID from memory — always `search-actors` first, since
exact IDs/availability change over time and this list is illustrative, not
authoritative.

### Gotchas
- Free tier: $5/month credits — Actor runs cost credits per result/compute
  time, more than a single crawl4ai/Firecrawl call. Don't reach for an Actor
  for a job a plain `scrape_url` could handle.
- Needs Node.js 18+ on the host (launched via `npx`).
