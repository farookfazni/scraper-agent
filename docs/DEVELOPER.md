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
| Agent construction & system prompt | `scraper/agent.py` (`_BASE_INSTRUCTIONS`, `ScraperAgent`) |
| Per-capability skill docs | `scraper/skills/*.md` (loaded by `scraper/skills/__init__.py`) |
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
2. Follow the existing contract: **return a string, never raise.** Use the established sentinel prefixes (`SCRAPE_ERROR:`, `SCRAPE_EMPTY:`, `TOOL_UNAVAILABLE:`, `SEARCH_ERROR:`) so the agent's fallback logic (defined in `_BASE_INSTRUCTIONS`) knows how to react. If your tool depends on an optional package or API key, check for it at call time and lazy-import so a missing dependency degrades to `TOOL_UNAVAILABLE` instead of an import-time crash.
3. Export it from `scraper/tools/__init__.py` (add to the imports and `__all__`).
4. Add it to the `all_tools` list in `ScraperAgent.__init__` (`scraper/agent.py`).
5. **Update `_BASE_INSTRUCTIONS`** in `scraper/agent.py` to tell the agent *when* to use it (add it to the relevant site_type row), and **update the relevant skill file** in `scraper/skills/` to document *how* (params, gotchas) — this is the step people forget. A tool that's registered but never mentioned anywhere in the prompt will rarely (if ever) get called, since the LLM has no instruction pointing it there.
6. If it changes the priority table for any `site_type`, update the table in `_BASE_INSTRUCTIONS`, `CLAUDE.md`, and `docs/ARCHITECTURE.md` together — they're kept in sync by convention, not by code.

### Add a new skill file

Skill files (`scraper/skills/*.md`) give the agent depth on one capability source — exact tool names, parameters, best-for scenarios, gotchas — separate from the site_type try-order table (which stays in `_BASE_INSTRUCTIONS`/`CLAUDE.md`/`docs/ARCHITECTURE.md`). Add one when a capability source (a new MCP server, or a meaningfully expanded Python tool) has enough depth that a one-line prompt mention isn't sufficient.

1. Write `scraper/skills/<name>.md` following the existing template: what it is → tools/actions available → best-for scenarios → gotchas/limits. Look at `scraper/skills/firecrawl_mcp.md` for a worked example.
2. If it's always relevant (not gated by an API key), add `"<name>"` to `_ALWAYS_ON_SKILLS` in `scraper/agent.py`. If it's tied to an MCP server, add `"<server_name>": "<skill_name>"` to `_MCP_SKILLS` — `server_name` must match the `name=` the server is constructed with in `mcp_servers/mcp_manager.py` (e.g. `"tavily"`, `"firecrawl"`, `"apify"`).
3. Don't repeat the site_type priority table inside the skill file — point back to it (`"see the PHASE 2 table above"`) if you need to reference ordering. Skills own single-capability depth, not cross-tool ordering.
4. If you author skill content based on external docs (an MCP server's own tool list, a library's parameter reference), verify against the *current* upstream source rather than trusting older documentation, examples, or blog posts — tool names and package names do change (this project's own Apify integration shipped with a wrong npm package name for a while because it wasn't re-verified against Apify's current docs).

### Add a new MCP server

1. Add a `build_<name>_mcp() -> MCPServerStdio | MCPServerStreamableHttp | None` function in `mcp_servers/mcp_manager.py`, returning `None` if the required API key/env isn't set (follow the existing three builders as templates). Give it an explicit `name=` — this is what `scraper/agent.py`'s skill-composition logic matches against.
2. Append it to the loop in `build_scraper_mcp_servers()`.
3. If it launches via `npx`, use the `_npx()` helper — it handles the Windows `cmd /c npx ...` indirection that direct `npx` subprocess spawning needs on this platform. Double-check the exact npm package name against the provider's current docs before shipping it.
4. Update `_BASE_INSTRUCTIONS` in `scraper/agent.py` so the agent knows *when* to reach for the new server (add/adjust a row in the site_type table).
5. Write a matching skill file (see "Add a new skill file" above) so the agent knows *how* to use its tools in depth, and register it in `_MCP_SKILLS`.
6. Document the new env var in `.env.example` and the config table in `README.md`.

### Add a new LLM provider

Add a `base_url` entry to the `base_urls` dict in `main.py`'s `_setup_client()`, and a provider-specific API key env var if you want one beyond the universal `API_KEY`. Document it in `.env.example`.

**If that provider's model IDs contain a literal `/`** (e.g. Groq's `groq/compound`, OpenRouter's `openrouter/openai/gpt-4o`), no extra work is needed — `scraper/agent.py`'s `_MODEL_PROVIDER` (a `MultiProvider(unknown_prefix_mode="model_id")`) already passes such strings through as-is instead of misreading the `/` as an SDK routing prefix (see `docs/ARCHITECTURE.md`'s `scraper/agent.py` section). Just set `SCRAPER_MODEL` to the provider's real model ID, slash and all.

**If that provider/model uses a text-based tool-call format** (some Groq models, notably `compound`, emit `<function=...><parameter=...>` blocks rather than native JSON), expect it to occasionally serialize typed values loosely — e.g. Python-style `"True"`/`"False"` strings instead of JSON `true`/`false` for boolean parameters, which a strict JSON schema will reject. `scraper/tools/crawl4ai_tool.py`'s boolean params (`magic`, `respect_robots_txt`, `remove_popups`, `exclude_external_links`, `scan_full_page`) are typed `bool | str` for exactly this reason, with a `_coerce_bool()` helper normalizing at the top of the function body. If you add a new boolean tool parameter and target a similarly loose model/provider, follow the same pattern rather than assuming `bool` alone is safe.

### Custom output fields

`ScrapeSpec.extract_fields` is open-ended and defaults to `{}` — callers can pin exact fields via `--fields` (CLI), but the REPL no longer prompts for it: when empty, the agent derives fields from `extraction_hint`/the user's plain-language goal, or falls back to a general-purpose summary shape (see `docs/ARCHITECTURE.md` §8). The JSON envelope itself (`status`/`data`/`sources`/`tools_used`/`errors`/`raw_text`) is fixed and shouldn't be changed without updating every consumer of `ScrapeOutput`.

### Passing extra tools/servers at runtime without forking the code

`ScraperAgent(extra_tools=[my_tool])` and `ScraperAgent(mcp_servers=[my_server, *build_scraper_mcp_servers()])` let you extend a single agent instance without touching `scraper/agent.py` — useful for one-off scripts or experiments.

## Known gaps / things to be careful about

These aren't bugs exactly, but they'll bite you if you don't know about them:

- **No test suite.** There's no `tests/` directory, no pytest config, nothing in CI. If you're adding a tool, there's no harness to validate it beyond running the REPL manually. If you're the one setting up testing, the natural seams are: (1) unit tests around `_parse_fields` and `save_result`'s filename sanitization (pure functions, no network), (2) mocking `Runner.run` to test `ScraperAgent.run()`'s output-path-recovery logic in isolation, (3) integration tests behind a marker that require real API keys/network.
- **Output-path recovery is string-matching, not structured.** `ScraperAgent.run()` finds the saved file by scanning the LLM's final text for `"Saved:"` + a `.json` path that exists on disk. If you change `save_result`'s return string format in `output_tool.py`, you **must** update the matching logic in `scraper/agent.py` at the same time, or every run will start reporting `status="failed"` even when the file was written correctly.
- **`_parse_fields` is duplicated** — once as a top-level function in `main.py`, and again inline inside `_repl()`. If you change field-parsing behavior (e.g. support new type names), update both, or better, refactor `_repl()` to call `_parse_fields()`.
- **Truncation limits differ across tool families** — `scrape_url`/`scrape_urls` now share `MAX_CONTENT_CHARS` (20k, defined in `crawl4ai_tool.py`), but `pdf_extract` (30k) and `fetch_url` (15k, no truncation marker) still use their own independent limits. If you're debugging "why did I get partial content," check which tool actually ran (`tools_used` in the output) and its specific limit.
- **`verify=False`** (TLS verification off) is hardcoded in `pdf_tool.py` and `fetch_tool.py`. This is a deliberate compatibility choice, not an oversight — but don't copy it into a new tool without thinking about whether it's appropriate for that use case.
- **The in-process cache has no eviction or TTL.** In a long-running REPL session or a server wrapping this agent, `scraper/tools/cache.py`'s `_CACHE` dict grows unbounded until `/reset` or process restart. Fine for a CLI tool; would need bounding before embedding in a long-lived service.
- **`APIFY_API_KEY` → `APIFY_TOKEN` env var rename** happens inside `build_apify_mcp()` when launching the subprocess — if you're debugging "Apify MCP can't find its key," remember the subprocess sees a differently-named variable than what you set in `.env`.
- **Apify's MCP server is discovery-based, not one-tool-per-actor.** It exposes `search-actors`/`fetch-actor-details`/`call-actor`/`get-dataset-items` etc., not fixed tools named after specific scrapers. `scraper/skills/apify_mcp.md` documents the real workflow — if you're debugging "the agent tried to call an actor name directly and failed," that's the mismatch to check for.
- **Tavily's MCP key travels as a URL query parameter** (`?tavilyApiKey=<key>`) in `build_tavily_mcp()`. Be mindful of this if you ever add request logging near that HTTP client — the key would end up in logs.
- **No `.gitignore` exists yet.** Before running anything that generates `output/*.json` or creating a local `.env`, add one covering at least `.venv/`, `__pycache__/`, `.env`, and `output/` to avoid accidentally committing secrets or scrape output.
- **Packaging**: `pyproject.toml`'s `[tool.setuptools.packages.find]` only includes `scraper*` and `mcp_servers*`, but the console-script entry point is `main:main` — `main.py` lives at the repo root, outside both packages. This works when running from a checked-out repo root, but if you ever `pip install .` from elsewhere and expect the `scraper-agent` console command to work, verify `main.py` actually gets packaged — it may need an explicit `py-modules = ["main"]` entry. Relatedly, `scraper/skills/*.md` are read from disk at runtime (`Path(__file__).parent`, not an embedded resource) — they'll be included automatically as long as `scraper*` package discovery picks up the `skills` subpackage, but if you ever add a `MANIFEST.in` or switch to a build backend with stricter package-data rules, make sure the `.md` files still ship.

## Style conventions to follow

- **Never raise from a tool.** Return a sentinel string instead (see the error-protocol table in `ARCHITECTURE.md` §5).
- **Lazy-import optional dependencies** inside the tool function, not at module top, so `TOOL_UNAVAILABLE` degrades gracefully instead of an `ImportError` at process startup.
- **Local imports in `main.py`** for `scraper`/`mcp_servers` modules are intentional — they happen after `_setup_client()` configures the global OpenAI client, so keep new top-level imports in `main.py` minimal and prefer local imports inside functions that need agent internals.
- Keep the tool-priority table in sync across three places whenever you touch it: `_BASE_INSTRUCTIONS` in `scraper/agent.py` (the source of truth the agent actually reads), `CLAUDE.md`, and `docs/ARCHITECTURE.md`. Skill files (`scraper/skills/*.md`) are a separate, fourth thing — they own per-capability depth, not the table — don't let them drift into re-describing tool ordering.
