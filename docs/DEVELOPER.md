# Developer Guide

Practical guidance for working on scraper-agent: local setup, how to extend it, known gaps, and gotchas. Read [ARCHITECTURE.md](ARCHITECTURE.md) first if you haven't — this doc assumes you know the request lifecycle and the sentinel-string error protocol.

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill in at minimum `PROVIDER` and one API key. For local dev without any cloud LLM cost, set `PROVIDER=ollama` and run a local Ollama server — no key needed.

Optional, only if you want the Python-client search fallbacks (not required for the MCP versions of Tavily/Firecrawl):

```bash
pip install tavily-python firecrawl-py
```

Optional, only if you want the Firecrawl or Apify **MCP** servers (not their Python fallbacks): Node.js 18+, since both launch via `npx -y <pkg>`.

Run the REPL for fast iteration:

```bash
python main.py
```

`/reset` inside the REPL clears the in-process tool cache (`scraper/tools/cache.py`) without restarting.

## Where things live (quick index)

| Concern | File |
| --- | --- |
| CLI args / REPL / provider setup | `main.py` |
| Job definition & output shape | `scraper/spec.py` (`ScrapeSpec`, `ScrapeOutput`) |
| Agent construction & system prompt | `scraper/agent.py` (`_INSTRUCTIONS`, `ScraperAgent`) |
| Browser/HTML scraping | `scraper/tools/crawl4ai_tool.py` |
| PDF extraction | `scraper/tools/pdf_tool.py` |
| Search backends | `scraper/tools/search_tool.py` |
| Plain HTTP fallback | `scraper/tools/fetch_tool.py` |
| Result persistence | `scraper/tools/output_tool.py` |
| Tool memoization | `scraper/tools/cache.py` |
| Optional MCP servers | `mcp_servers/mcp_manager.py` |

## Extending

### Add a new Python tool

1. Write an `async` (or sync, if it's cheap/blocking-safe like `fetch_url`) function in a file under `scraper/tools/`, decorated `@function_tool` (from the `agents` SDK). Add `@cached_tool` too if the operation is idempotent and worth memoizing.
2. Follow the existing contract: **return a string, never raise.** Use the established sentinel prefixes (`SCRAPE_ERROR:`, `SCRAPE_EMPTY:`, `TOOL_UNAVAILABLE:`, `SEARCH_ERROR:`) so the agent's fallback logic (defined in `_INSTRUCTIONS`) knows how to react. If your tool depends on an optional package or API key, check for it at call time and lazy-import so a missing dependency degrades to `TOOL_UNAVAILABLE` instead of an import-time crash.
3. Export it from `scraper/tools/__init__.py` (add to the imports and `__all__`).
4. Add it to the `all_tools` list in `ScraperAgent.__init__` (`scraper/agent.py`).
5. **Update `_INSTRUCTIONS`** in `scraper/agent.py` to tell the agent when to use it — this is the step people forget. A tool that's registered but never mentioned in the prompt will rarely (if ever) get called, since the LLM has no instruction pointing it there.
6. If it changes the priority table for any `site_type`, update the table in `_INSTRUCTIONS`, `CLAUDE.md`, and `docs/ARCHITECTURE.md` together — they're kept in sync by convention, not by code.

### Add a new MCP server

1. Add a `build_<name>_mcp() -> MCPServerStdio | MCPServerStreamableHttp | None` function in `mcp_servers/mcp_manager.py`, returning `None` if the required API key/env isn't set (follow the existing three builders as templates).
2. Append it to the loop in `build_scraper_mcp_servers()`.
3. If it launches via `npx`, use the `_npx()` helper — it handles the Windows `cmd /c npx ...` indirection that direct `npx` subprocess spawning needs on this platform.
4. Update `_INSTRUCTIONS` in `scraper/agent.py` so the agent knows what tools the new server exposes and when to prefer them.
5. Document the new env var in `.env.example` and the config table in `README.md`.

### Add a new LLM provider

Add a `base_url` entry to the `base_urls` dict in `main.py`'s `_setup_client()`, and a provider-specific API key env var if you want one beyond the universal `API_KEY`. Document it in `.env.example`.

### Custom output fields

`ScrapeSpec.extract_fields` is open-ended — callers define whatever fields they want at request time (via `--fields` or the REPL prompt). The JSON envelope itself (`status`/`data`/`sources`/`tools_used`/`errors`/`raw_text`) is fixed and shouldn't be changed without updating every consumer of `ScrapeOutput`.

### Passing extra tools/servers at runtime without forking the code

`ScraperAgent(extra_tools=[my_tool])` and `ScraperAgent(mcp_servers=[my_server, *build_scraper_mcp_servers()])` let you extend a single agent instance without touching `scraper/agent.py` — useful for one-off scripts or experiments.

## Known gaps / things to be careful about

These aren't bugs exactly, but they'll bite you if you don't know about them:

- **No test suite.** There's no `tests/` directory, no pytest config, nothing in CI. If you're adding a tool, there's no harness to validate it beyond running the REPL manually. If you're the one setting up testing, the natural seams are: (1) unit tests around `_parse_fields` and `save_result`'s filename sanitization (pure functions, no network), (2) mocking `Runner.run` to test `ScraperAgent.run()`'s output-path-recovery logic in isolation, (3) integration tests behind a marker that require real API keys/network.
- **Output-path recovery is string-matching, not structured.** `ScraperAgent.run()` finds the saved file by scanning the LLM's final text for `"Saved:"` + a `.json` path that exists on disk. If you change `save_result`'s return string format in `output_tool.py`, you **must** update the matching logic in `scraper/agent.py` at the same time, or every run will start reporting `status="failed"` even when the file was written correctly.
- **`_parse_fields` is duplicated** — once as a top-level function in `main.py`, and again inline inside `_repl()`. If you change field-parsing behavior (e.g. support new type names), update both, or better, refactor `_repl()` to call `_parse_fields()`.
- **Truncation limits differ across tools** with no documented rationale (`scrape_url` 20k chars, `scrape_urls` 15k/URL, `pdf_extract` 30k, `fetch_url` 15k with no truncation marker). If you're debugging "why did I get partial content," check which tool actually ran (`tools_used` in the output) and its specific limit.
- **`verify=False`** (TLS verification off) is hardcoded in `pdf_tool.py` and `fetch_tool.py`. This is a deliberate compatibility choice, not an oversight — but don't copy it into a new tool without thinking about whether it's appropriate for that use case.
- **The in-process cache has no eviction or TTL.** In a long-running REPL session or a server wrapping this agent, `scraper/tools/cache.py`'s `_CACHE` dict grows unbounded until `/reset` or process restart. Fine for a CLI tool; would need bounding before embedding in a long-lived service.
- **`APIFY_API_KEY` → `APIFY_TOKEN` env var rename** happens inside `build_apify_mcp()` when launching the subprocess — if you're debugging "Apify MCP can't find its key," remember the subprocess sees a differently-named variable than what you set in `.env`.
- **Tavily's MCP key travels as a URL query parameter** (`?tavilyApiKey=<key>`) in `build_tavily_mcp()`. Be mindful of this if you ever add request logging near that HTTP client — the key would end up in logs.
- **No `.gitignore` exists yet.** Before running anything that generates `output/*.json` or creating a local `.env`, add one covering at least `.venv/`, `__pycache__/`, `.env`, and `output/` to avoid accidentally committing secrets or scrape output.
- **Packaging**: `pyproject.toml`'s `[tool.setuptools.packages.find]` only includes `scraper*` and `mcp_servers*`, but the console-script entry point is `main:main` — `main.py` lives at the repo root, outside both packages. This works when running from a checked-out repo root, but if you ever `pip install .` from elsewhere and expect the `scraper-agent` console command to work, verify `main.py` actually gets packaged — it may need an explicit `py-modules = ["main"]` entry.

## Style conventions to follow

- **Never raise from a tool.** Return a sentinel string instead (see the error-protocol table in `ARCHITECTURE.md` §5).
- **Lazy-import optional dependencies** inside the tool function, not at module top, so `TOOL_UNAVAILABLE` degrades gracefully instead of an `ImportError` at process startup.
- **Local imports in `main.py`** for `scraper`/`mcp_servers` modules are intentional — they happen after `_setup_client()` configures the global OpenAI client, so keep new top-level imports in `main.py` minimal and prefer local imports inside functions that need agent internals.
- Keep the tool-priority table in sync across three places whenever you touch it: `_INSTRUCTIONS` in `scraper/agent.py` (the source of truth the agent actually reads), `CLAUDE.md`, and `docs/ARCHITECTURE.md`.
