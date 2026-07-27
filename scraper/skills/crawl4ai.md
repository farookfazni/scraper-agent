## SKILL: crawl4ai (always available, Python tools, no API key)

crawl4ai is a headless-browser scraper — it renders JavaScript, so it works on
pages plain HTTP can't (fetch_url can't). It's your default, general-purpose
scraper when no MCP tool is mounted or better suited. Four tools:

### scrape_url(url, wait_for=None, js_code=None, session_id=None, magic=False, word_count_threshold=50, respect_robots_txt=False, remove_popups=False, css_selector=None, excluded_tags=None, exclude_external_links=False, scan_full_page=False)
Scrapes ONE URL, returns clean markdown (prefers crawl4ai's cleaned
`fit_markdown`, falls back to raw markdown). Content is capped at 20,000
chars (truncation marker appended if cut).

Param guidance:
- `wait_for` — CSS selector or `js:<expr>` to wait for before extracting. Use
  for React/Vue/Angular pages that render content after initial load.
  Example: `'table.financial-data'` or `'js:document.querySelector(".data")'`
- `js_code` — JS to run before extracting (click "load more", expand a
  section, dismiss a modal manually). KEEP IT SIMPLE: a short single
  expression, one quote style only. Avoid nested/escaped quotes (e.g.
  `document.querySelectorAll('[aria-label=\"X\"]')` mixing ' and ") — on some
  models this breaks tool-call generation itself, not just execution. Prefer
  selectors with no quoted attribute values, or keep everything in one quote
  style. If a call with js_code fails, retry once with js_code omitted before
  trying a different tool.
- `session_id` — pass the same arbitrary string across multiple calls to
  preserve login/cookies between them (e.g. login page then a data page).
  This is DIFFERENT from ScrapeSpec's `use_session` field (a bool) — if that
  flag is true, invent a session_id string yourself and reuse it across
  calls; never pass a boolean into scrape_url's session_id parameter.
- `magic` — turns on anti-bot heuristics (simulated mouse movement, spoofed
  navigator properties). Try this before giving up on a site that returns
  empty/blocked content.
- `respect_robots_txt` — set True when scraping a site you don't operate and
  compliance matters. Default False (matches this project's historical
  behavior — robots.txt is NOT checked unless you opt in).
- `remove_popups` — strip cookie-consent banners and modal overlays before
  extracting. Turn this on for EU news/e-commerce sites where a consent
  banner often pollutes the top of the scraped markdown.
- `css_selector` — scope extraction to one container, e.g. `'main.report'` or
  `'#content'`. Use on pages with heavy nav/sidebar/ad noise, especially
  `table`/`financial` site_types where you know the data lives in one place.
- `excluded_tags` — comma-separated tag names to drop entirely, e.g.
  `'nav,footer,aside'`. Cheaper/coarser than css_selector; use when you don't
  know a specific container but know what to exclude.
- `exclude_external_links` — drop off-domain links from the output markdown.
  Use when link noise (not link data) is the problem.
- `scan_full_page` — auto-scrolls before extracting. Use for feeds/listings
  that lazy-load more content as you scroll (social feeds, infinite product
  listings). Slower — only use when content is actually missing without it.

Failure modes: `SCRAPE_ERROR: crawl4ai — <reason>` (network/render failure,
try the next tool in the priority order), `SCRAPE_EMPTY: ...` (page rendered
but had no usable text — try enabling `magic`/`remove_popups`/`wait_for`
before falling back to a different tool entirely).

### scrape_urls(urls_json)
Same engine, parallel fetch for 3+ URLs via crawl4ai's `arun_many`. Takes a
JSON array of URL strings, returns a JSON array of `{url, status, content}`.
Each URL's content is capped at 20,000 chars, same as scrape_url. Does NOT
currently support the extra params above (wait_for/js_code/magic/etc.) —
those are single-URL only; if a batch needs special handling, scrape those
URLs individually with scrape_url instead.

### extract_structured(url, css_schema_json)
Pure CSS-selector extraction — no LLM involved, fast and deterministic. Best
for pages where you already know the exact HTML structure (e.g. a stable
data table). Schema shape:
```json
{
  "name": "schema_name",
  "baseSelector": "table.data tr",
  "fields": [
    {"name": "year", "selector": "td:nth-child(1)", "type": "text"},
    {"name": "revenue", "selector": "td:nth-child(2)", "type": "text"}
  ]
}
```
Returns a JSON array, one object per matched `baseSelector` element. Use this
before `scrape_url` for `site_type="table"` pages when you can identify the
selectors from the page structure — it's faster and more precise than
free-text extraction from markdown.

### crawl_paginated(start_url, max_pages=5, url_pattern=None, same_domain_only=True, word_count_threshold=50)
Deterministic multi-page crawl for NUMBERED PAGINATION (page 1, 2, 3, ... via
real links) — built on crawl4ai's own BFS deep-crawl engine, not prompt-guessed
URL construction. **This is the primary tool for "list all X across every
page" requests** — don't manually build page URLs and loop `scrape_urls`
yourself; that's unreliable (you'll often only get page 1). Use this instead.

Param guidance:
- `url_pattern` — a glob matching ONLY the actual pagination link hrefs you
  saw on the first page, e.g. `'*page=*'` or `'*/page/*'`. **Read the real
  pagination links first, then build this from them** — don't guess a
  pattern you haven't actually seen. Without one, the crawl falls back to
  same-domain-scoping alone, which may pick up unrelated nav/footer links
  instead of just the next pages — still usable as a safety net, but less
  precise.
- `max_pages` — total pages to visit, INCLUDING the start page. Set this to
  the real total you saw (e.g. "Page 1 of 5" → 5), not an arbitrarily large
  number — this isn't a general site crawler, don't let it wander.
- `same_domain_only` — leave True almost always; pagination stays on-site.

Returns the same shape as `scrape_urls`: a JSON array of `{url, status,
content}`, one entry per page actually crawled — merge every page's items
into one combined list in `data` before calling save_result. Only ever
crawls one hop from `start_url` (depth=1) — it follows pagination links, not
a general multi-level site crawl (use Firecrawl's `firecrawl_crawl` MCP tool
for that instead, if mounted).

Failure modes: `SCRAPE_EMPTY: ...` if `url_pattern` matched nothing (check
it against the real hrefs again), `SCRAPE_ERROR: ...` on a crawl failure —
fall back to manually building page URLs + `scrape_urls` only as a last
resort if this tool itself is unavailable.

Gotcha: all four tools are Python function calls, not an MCP server —
there's no separate connection/auth step, they're always in your tool list.
