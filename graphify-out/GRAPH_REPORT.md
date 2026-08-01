# Graph Report - scraper-agent  (2026-08-01)

## Corpus Check
- 32 files · ~18,799 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 182 nodes · 265 edges · 15 communities (14 shown, 1 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 15 edges (avg confidence: 0.7)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `fffd02db`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- tools/__init__.py
- agent.py
- build_scraper_mcp_servers
- Architecture Report
- scraper-agent
- main.py
- Extending
- CLAUDE.md
- search_tool.py
- SKILL: Firecrawl MCP (mounted — FIRECRAWL_API_KEY is set)
- SKILL: search, PDF, and fallback tools (always available, Python)
- SKILL: Apify MCP (mounted — APIFY_API_KEY is set)
- SKILL: crawl4ai (always available, Python tools, no API key)
- SKILL: Tavily MCP (mounted — TAVILY_API_KEY is set)
- scraper-agent

## God Nodes (most connected - your core abstractions)
1. `ScrapeSpec` - 11 edges
2. `ScraperAgent` - 10 edges
3. `scraper-agent` - 10 edges
4. `build_scraper_mcp_servers()` - 9 edges
5. `cached_tool()` - 9 edges
6. `scrape_url()` - 9 edges
7. `Architecture Report` - 9 edges
8. `extract_structured()` - 8 edges
9. `crawl_paginated()` - 8 edges
10. `_repl()` - 7 edges

## Surprising Connections (you probably didn't know these)
- `_run_once()` --calls--> `build_scraper_mcp_servers()`  [EXTRACTED]
  main.py → mcp_servers/mcp_manager.py
- `_run_once()` --calls--> `ScraperAgent`  [EXTRACTED]
  main.py → scraper/agent.py
- `_run_once()` --calls--> `ScrapeSpec`  [EXTRACTED]
  main.py → scraper/spec.py
- `_repl()` --calls--> `build_scraper_mcp_servers()`  [EXTRACTED]
  main.py → mcp_servers/mcp_manager.py
- `_repl()` --calls--> `ScraperAgent`  [EXTRACTED]
  main.py → scraper/agent.py

## Import Cycles
- None detected.

## Communities (15 total, 1 thin omitted)

### Community 0 - "tools/__init__.py"
Cohesion: 0.10
Nodes (29): graphify, cached_tool(), In-process memoization for scraper tools. Keyed by MD5(fn_name + args) —…, Decorator that caches the return value of a tool function. Works for both sync…, _coerce_bool(), crawl_paginated(), extract_structured(), _import_crawl4ai() (+21 more)

### Community 1 - "agent.py"
Cohesion: 0.14
Nodes (16): BaseModel, _compose_instructions(), ScraperAgent — a universal, configurable web scraping agent. Usage ----- from…, Build the final system prompt: base phase/rules skeleton + skill docs. Always-…, Universal web scraping agent. Parameters ---------- model : str LLM model.…, Run a scraping job from a ScrapeSpec and return a ScrapeOutput. Parameters…, ScraperAgent, load_skill() (+8 more)

### Community 2 - "build_scraper_mcp_servers"
Cohesion: 0.20
Nodes (13): build_apify_mcp(), build_firecrawl_mcp(), build_scraper_mcp_servers(), build_tavily_mcp(), _npx(), MCP server manager for scraper-agent. Three optional web-scraping MCP servers —…, Return all configured MCP servers. Servers whose API key is missing are…, Build MCPServerStdio params for an npx-launched server. Windows-safe. (+5 more)

### Community 3 - "Architecture Report"
Cohesion: 0.14
Nodes (14): 1. The core idea, 2. Request lifecycle, 3. Component map, 4. File-by-file, 5. Design tradeoffs worth knowing, 6. Output contract, 7. Skills layer, 8. Zero-config input — the agent infers what a regular user shouldn't have to know (+6 more)

### Community 4 - "scraper-agent"
Cohesion: 0.17
Nodes (10): Configuration, Example, Features, How it works, in short, License, Project layout, Quickstart, Requirements (+2 more)

### Community 5 - "main.py"
Cohesion: 0.24
Nodes (12): _default_schema_name(), main(), _parse_fields(), scraper-agent CLI — interactive REPL and programmatic entry point. Usage -----…, Auto-generate a filename-friendly schema name from a URL or search query, so a…, Parse "title:string,price:number" into {"title": "string", "price": "number"}., Configure the OpenAI-compatible client from PROVIDER env var., _repl() (+4 more)

### Community 6 - "Extending"
Cohesion: 0.17
Nodes (12): Add a new LLM provider, Add a new MCP server, Add a new Python tool, Add a new skill file, Custom output fields, Developer Guide, Extending, Known gaps / things to be careful about (+4 more)

### Community 7 - "CLAUDE.md"
Cohesion: 0.18
Nodes (9): Architecture, Configuration, Extending, graphify, Key Files, Output JSON Schema, Running, Setup (+1 more)

### Community 8 - "search_tool.py"
Cohesion: 0.28
Nodes (8): duckduckgo_search(), firecrawl_search(), function_tool, Search tools — find URLs before scraping. Priority: 1. Tavily (TAVILY_API_KEY)…, Search the web using Tavily — best for financial news, annual reports, IR…, Search the web using DuckDuckGo — always available, no API key needed. Args:…, Search using Firecrawl — fallback when Tavily and DuckDuckGo are insufficient.…, tavily_search()

### Community 9 - "SKILL: Firecrawl MCP (mounted — FIRECRAWL_API_KEY is set)"
Cohesion: 0.25
Nodes (7): firecrawl_crawl, firecrawl_deep_research, firecrawl_extract, firecrawl_scrape, firecrawl_search, Gotchas, SKILL: Firecrawl MCP (mounted — FIRECRAWL_API_KEY is set)

### Community 10 - "SKILL: search, PDF, and fallback tools (always available, Python)"
Cohesion: 0.25
Nodes (7): duckduckgo_search(query, max_results=5), fetch_url(url), firecrawl_search(query, max_results=5), pdf_extract(url), save_result(result_json, schema_name, output_dir="output"), SKILL: search, PDF, and fallback tools (always available, Python), tavily_search(query, max_results=5)

### Community 11 - "SKILL: Apify MCP (mounted — APIFY_API_KEY is set)"
Cohesion: 0.33
Nodes (5): Core workflow tools, Gotchas, SKILL: Apify MCP (mounted — APIFY_API_KEY is set), Supporting tools, When to reach for Apify instead of crawl4ai/Firecrawl

### Community 12 - "SKILL: crawl4ai (always available, Python tools, no API key)"
Cohesion: 0.33
Nodes (5): crawl_paginated(start_url, max_pages=5, url_pattern=None, same_domain_only=True, word_count_threshold=50), extract_structured(url, css_schema_json), scrape_url(url, wait_for=None, js_code=None, session_id=None, magic=False, word_count_threshold=50, respect_robots_txt=False, remove_popups=False, css_selector=None, excluded_tags=None, exclude_external_links=False, scan_full_page=False), scrape_urls(urls_json), SKILL: crawl4ai (always available, Python tools, no API key)

### Community 13 - "SKILL: Tavily MCP (mounted — TAVILY_API_KEY is set)"
Cohesion: 0.33
Nodes (5): extract, Gotchas, Possibly also available: map / crawl, search, SKILL: Tavily MCP (mounted — TAVILY_API_KEY is set)

## Knowledge Gaps
- **66 isolated node(s):** `scraper-agent`, `graphify`, `Setup`, `Running`, `Architecture` (+61 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `build_scraper_mcp_servers()` connect `build_scraper_mcp_servers` to `main.py`?**
  _High betweenness centrality (0.072) - this node is a cross-community bridge._
- **Why does `ScraperAgent` connect `agent.py` to `tools/__init__.py`, `main.py`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Why does `ScrapeSpec` connect `agent.py` to `main.py`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `ScraperAgent` (e.g. with `ScrapeOutput` and `ScrapeSpec`) actually correct?**
  _`ScraperAgent` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `build_scraper_mcp_servers()` (e.g. with `build_apify_mcp()` and `build_firecrawl_mcp()`) actually correct?**
  _`build_scraper_mcp_servers()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `scraper-agent`, `graphify`, `Setup` to the rest of the system?**
  _66 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `tools/__init__.py` be split into smaller, more focused modules?**
  _Cohesion score 0.10241820768136557 - nodes in this community are weakly interconnected._