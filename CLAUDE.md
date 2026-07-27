# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
playwright install chromium     # required — crawl4ai's browser binary, not installed by pip alone
copy .env.example .env          # fill in PROVIDER + API key
```

For optional Tavily / Firecrawl search: `pip install tavily-python firecrawl-py`

## Running

```bash
python main.py                  # interactive REPL — just a URL/query + optional goal
python main.py "https://example.com/report.pdf"   # simplest form — agent infers site_type/fields itself
python main.py "https://example.com/report.pdf" --schema report --fields "revenue:number,npat:number"  # manual override
```

## Architecture

One agent, a composable tool layer (Python tools + optional MCP servers), fixed output schema.

```text
main.py  (CLI / REPL)
  └── build_scraper_mcp_servers()   # mcp_servers/mcp_manager.py
  └── ScraperAgent(mcp_servers=...) # scraper/agent.py
        ├── MCP servers (optional, mounted when API key is present)
        │     ├── tavily MCP        — search + extract (StreamableHttp)
        │     ├── firecrawl MCP     — scrape/crawl/deep_research/extract (stdio/npx)
        │     └── apify MCP         — actor discovery: search-actors/call-actor/etc. (stdio/npx)
        ├── scraper/skills/*.md      — per-capability docs, conditionally composed into the prompt
        └── Python tools (always available)
              ├── scrape_url          — single URL, full crawl4ai options
              ├── scrape_urls         — parallel batch via arun_many
              ├── extract_structured  — CSS-selector table extraction
              ├── crawl_paginated     — deterministic multi-page crawl (numbered pagination)
              ├── pdf_extract         — pdfplumber → pymupdf4llm fallback
              ├── duckduckgo_search   — always available, no key
              ├── tavily_search       — Python client (fallback if MCP absent)
              ├── firecrawl_search    — Python client (fallback if MCP absent)
              ├── fetch_url           — plain HTTP, last resort
              └── save_result         — writes output/{schema}_{ts}.json
```

## Key Files

| File | Purpose |
| --- | --- |
| `scraper/spec.py` | `ScrapeSpec` (job definition) and `ScrapeOutput` (parsed result) Pydantic models |
| `scraper/agent.py` | `ScraperAgent` class — wraps the SDK `Agent`, holds tool list + mcp_servers, composes skill docs into the prompt, parses output |
| `scraper/skills/` | Per-capability reference docs (crawl4ai, search/fetch, tavily/firecrawl/apify MCP) — loaded conditionally based on mounted MCP servers |
| `mcp_servers/mcp_manager.py` | `build_scraper_mcp_servers()` — builds Tavily/Firecrawl/Apify MCP server instances |
| `scraper/tools/crawl4ai_tool.py` | `scrape_url`, `scrape_urls`, `extract_structured`, `crawl_paginated` — full crawl4ai feature set |
| `scraper/tools/pdf_tool.py` | `pdf_extract` — pdfplumber + pymupdf4llm |
| `scraper/tools/search_tool.py` | `tavily_search`, `duckduckgo_search`, `firecrawl_search` (Python client fallbacks) |
| `scraper/tools/fetch_tool.py` | `fetch_url` — plain httpx GET, last resort |
| `scraper/tools/output_tool.py` | `save_result` — injects `_meta`, writes JSON |
| `scraper/tools/cache.py` | `@cached_tool` — MD5-keyed in-process memoization |
| `main.py` | CLI arg parser + interactive REPL |

## Output JSON Schema

Every run produces `output/{schema_name}_{timestamp}.json` with this envelope:

```json
{
  "_meta": { "schema_name": "...", "saved_at": "...", "version": "1.0" },
  "status": "success | partial | failed",
  "data": { "field": "value" },
  "sources": ["url1"],
  "tools_used": ["scrape_url"],
  "errors": [],
  "raw_text": null
}
```

## Configuration

| Env Var | Default | Purpose |
| --- | --- | --- |
| `PROVIDER` | `openai` | LLM provider |
| `API_KEY` | — | Universal API key (overrides provider-specific) |
| `SCRAPER_MODEL` | `gpt-4o-mini` | Model passed to `ScraperAgent` |
| `TAVILY_API_KEY` | — | Enables Tavily MCP (`search` + `extract`) and `tavily_search` Python tool |
| `FIRECRAWL_API_KEY` | — | Enables Firecrawl MCP (`firecrawl_scrape/crawl/extract/deep_research`) and `firecrawl_search` Python tool |
| `APIFY_API_KEY` | — | Enables Apify MCP (actor discovery — 3,000+ pre-built scrapers found via `search-actors`) |

Ten providers: `openai`, `groq`, `openrouter`, `gemini`, `ollama`, `together`, `deepseek`, `nvidia`, `huggingface`, `cerebras`.

## Tool Priority Order

| site_type | Phase 1 (search) | Phase 2 (scrape) |
| --- | --- | --- |
| `pdf` | skip | pdf_extract → firecrawl_scrape (MCP) → scrape_url → fetch_url |
| `table` | skip | firecrawl_extract (MCP) → extract_structured → scrape_url |
| `financial` | tavily MCP → ddg | tavily extract (MCP) → firecrawl_scrape (MCP) → scrape_url → fetch_url |
| `news` | tavily MCP → ddg | tavily extract (MCP) → firecrawl_scrape (MCP) → scrape_url → fetch_url |
| `ecommerce` | ddg | apify MCP (search-actors → call-actor) → scrape_url → fetch_url |
| `general` | ddg | scrape_url → fetch_url |
| any (URL given) | skip | per site_type above |
| any (3+ URLs) | skip | scrape_urls (parallel) |
| multi-page crawl | — | firecrawl_crawl (MCP) |
| paginated listing (detected after 1st scrape) | — | firecrawl_crawl (MCP) → crawl_paginated (crawl4ai deep-crawl) → manual scrape_urls (last resort) |
| deep research | — | firecrawl_deep_research (MCP) |

The agent checks for pagination signals (page numbers, Next/Prev, "Page X of Y") after every first scrape, not just when explicitly asked. It now uses `crawl_paginated` — a deterministic tool built on crawl4ai's own `BFSDeepCrawlStrategy` — to actually follow the pagination links, rather than inferring a URL pattern itself and looping `scrape_urls` (that approach proved unreliable and often returned only page 1).

MCP columns apply only when the relevant API key is set. Without any keys, the agent always has crawl4ai + DuckDuckGo.

## Extending

- **New Python tool** — add `@function_tool` in `scraper/tools/`, export from `scraper/tools/__init__.py`, add to `all_tools` in `scraper/agent.py`.
- **New MCP server** — add a builder (with an explicit `name=`) in `mcp_servers/mcp_manager.py`, append to `build_scraper_mcp_servers()`, add a matching skill file under `scraper/skills/` and register it in `_MCP_SKILLS` (`scraper/agent.py`).
- **New/updated skill doc** — edit `scraper/skills/*.md` for per-tool depth (params, gotchas); keep the site_type try-order table itself in `_BASE_INSTRUCTIONS` only, not in skill files.
- **New provider** — add `base_url` mapping in `main.py`'s `_setup_client()`.
- **Custom output fields** — extend `ScrapeSpec.extract_fields`; the JSON envelope is fixed, `data` is open.
- **Extra tools at runtime** — pass `extra_tools=[my_tool]` to `ScraperAgent(extra_tools=...)`.
- **Extra MCP servers at runtime** — pass `mcp_servers=[my_server, *build_scraper_mcp_servers()]` to `ScraperAgent(...)`.
