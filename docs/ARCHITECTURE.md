# Architecture Report

This document explains **what scraper-agent is, why it's built the way it is, and how it behaves at runtime.** It's aimed at someone who has never seen the codebase and wants a complete mental model before touching code.

## 1. The core idea

Traditional scrapers are pipelines written in code: `if site == X: use parser A; elif site == Y: use parser B`. That works until site structure changes or a new site type shows up — then you edit Python.

scraper-agent inverts this: there is **one LLM agent** with a fixed toolbox (9 Python functions + whatever MCP servers are configured), and a **system prompt** that tells the agent, in natural language, what order to try tools in for a given `site_type`, and what to do when a tool fails. The agent — not a Python dispatcher — decides which tool to call next, based on the prompt and the tool's return value.

This has one big consequence worth internalizing before reading any code: **the "routing logic" you'd expect to find as an `if/elif` chain in `agent.py` doesn't exist there.** It lives entirely inside the `_INSTRUCTIONS` string in `scraper/agent.py`. If you want to change fallback order, you edit that prompt text, not control flow.

## 2. Request lifecycle

```
User input (URL / query + desired fields)
        │
        ▼
main.py: build ScrapeSpec(target, site_type, extract_fields, ...)
        │
        ▼
mcp_servers.build_scraper_mcp_servers()   # mounts Tavily/Firecrawl/Apify MCP servers if keys present
        │
        ▼
ScraperAgent(mcp_servers=...)             # constructs an `Agent` from the openai-agents SDK
        │
        ▼
agent.run(spec)
   │
   ├─ prompt = "SCRAPE SPEC:\n" + spec.to_prompt_block()   # spec serialized as JSON
   │
   ├─ Runner.run(agent, input=prompt, max_turns=30)         # the actual agentic loop
   │     │
   │     ├─ PHASE 1 (search, only if target isn't a URL)
   │     ├─ PHASE 2 (scrape, tool order depends on site_type)
   │     ├─ PHASE 3 (extract fields per extract_fields)
   │     └─ PHASE 4 (call save_result exactly once)
   │
   └─ post-process: find "Saved: <path>.json" in the agent's final text,
      re-read that file, wrap it as ScrapeOutput
        │
        ▼
main.py prints status / data / errors, and the saved file path
```

Every phase above is a section of the system prompt — not a Python function. `Runner.run()` is the OpenAI Agents SDK's agentic loop: it repeatedly calls the LLM, executes whichever tool(s) it asks for, feeds results back, until the LLM produces a final answer or `max_turns` (30) is hit.

## 3. Component map

```text
main.py  (CLI / REPL)
  └── build_scraper_mcp_servers()   # mcp_servers/mcp_manager.py
  └── ScraperAgent(mcp_servers=...) # scraper/agent.py
        ├── MCP servers (optional, mounted only when the matching API key is present)
        │     ├── tavily MCP        — search + extract (StreamableHttp, remote)
        │     ├── firecrawl MCP     — scrape/crawl/deep_research/extract (stdio, via npx)
        │     └── apify MCP         — 3,000+ site-specific scrapers (stdio, via npx)
        └── Python tools (always registered, self-report TOOL_UNAVAILABLE if their key/package is missing)
              ├── scrape_url          — single URL, full crawl4ai (headless browser) options
              ├── scrape_urls         — parallel batch via crawl4ai's arun_many
              ├── extract_structured  — CSS-selector table extraction, no LLM involved
              ├── pdf_extract         — pdfplumber → pymupdf4llm fallback
              ├── duckduckgo_search   — always available, no key required
              ├── tavily_search       — Python client fallback (used if Tavily MCP isn't mounted)
              ├── firecrawl_search    — Python client fallback (used if Firecrawl MCP isn't mounted)
              ├── fetch_url           — plain HTTP GET, last resort (no JS rendering)
              └── save_result         — writes output/{schema}_{timestamp}.json
```

## 4. File-by-file

### `main.py` — CLI / REPL entry point

Two run modes, both funneling into the same `ScraperAgent`:

- **Argv mode** (`python main.py "<target>" --schema ... --fields ...`) → `_run_once()`: builds one `ScrapeSpec`, runs the agent once, prints results, exits.
- **REPL mode** (`python main.py` with no target) → `_repl()`: builds **one** `ScraperAgent` and reuses it across turns (so its underlying LLM session/tool wiring persists), prompting for `site_type`, `schema_name`, `fields`, `hint` each turn. Supports `/quit`, `/exit`, `/reset` (clears the in-process tool cache).

Before any of this runs, `_setup_client()` executes first — it reads `PROVIDER` (default `openai`), resolves an API key (`API_KEY` env var takes priority over provider-specific ones like `OPENAI_API_KEY`), and configures the OpenAI Agents SDK's global client to point at the right `base_url` for that provider:

```python
base_urls = {
    "openai":      "https://api.openai.com/v1",
    "groq":        "https://api.groq.com/openai/v1",
    "openrouter":  "https://openrouter.ai/api/v1",
    "gemini":      "https://generativelanguage.googleapis.com/v1beta/openai",
    "ollama":      "http://localhost:11434/v1",
    "together":    "https://api.together.xyz/v1",
    "deepseek":    "https://api.deepseek.com/v1",
    "nvidia":      "https://integrate.api.nvidia.com/v1",
    "huggingface": "https://api-inference.huggingface.co/v1",
    "cerebras":    "https://api.cerebras.ai/v1",
}
```

This is what makes the project provider-agnostic: any provider with an OpenAI-compatible `/chat/completions` endpoint works by pointing `base_url` at it. If no key is found (and the provider isn't `ollama`, which doesn't need one), the process exits with an error — there's no silent degraded mode here. If the provider isn't `openai`, tracing is disabled, since the SDK's tracing normally reports to OpenAI's platform.

### `scraper/spec.py` — the two data contracts

- **`ScrapeSpec`** — the job definition. Holds `target`, `site_type` (one of `financial|news|ecommerce|pdf|table|general`), `extract_fields` (a `dict[str, str]` of field name → type hint), plus browser-control knobs (`wait_for`, `js_code`, `use_session`, `magic`) that get threaded through to crawl4ai. `to_prompt_block()` serializes the whole thing to indented JSON — this JSON block is injected verbatim into the LLM's prompt, so the agent literally reads your spec as structured text.
- **`ScrapeOutput`** — the fixed result envelope: `status`, `data`, `sources`, `tools_used`, `errors`, `raw_text`, plus a loosely-typed `meta` dict. This is the shape every run returns, regardless of which tools were used internally.

### `scraper/agent.py` — the orchestrator

This is the file that matters most for understanding "why it works this way."

**`_INSTRUCTIONS`** is a multi-phase system prompt, not code:

| Phase | What it tells the LLM to do |
| --- | --- |
| 0 | Read the injected `ScrapeSpec` fields |
| 1 (search) | Only if `target` isn't already a URL: try MCP `tavily.search` → MCP `firecrawl_search` → Python `tavily_search` → `duckduckgo_search` → Python `firecrawl_search`, stop once 2–3 good URLs are found |
| 2 (scrape) | Tool order branches by `site_type` (see table below) |
| 3 (extract) | Pull `extract_fields` from scraped content per the type hints and `extraction_hint`; **never invent values** — use `null` for anything missing |
| 4 (save) | Call `save_result` **exactly once** with the fixed envelope shape |

Phase 2's per-`site_type` tool priority (this table is duplicated from `CLAUDE.md` since it's the single most important piece of runtime behavior to have front-of-mind):

| site_type | Phase 1 (search) | Phase 2 (scrape) |
| --- | --- | --- |
| `pdf` | skip | `pdf_extract` → MCP `firecrawl_scrape` → `scrape_url` → `fetch_url` |
| `table` | skip | MCP `firecrawl_extract` → `extract_structured` → `scrape_url` |
| `financial` | tavily MCP → ddg | MCP tavily `extract` → MCP `firecrawl_scrape` → `scrape_url` → `fetch_url` |
| `news` | tavily MCP → ddg | MCP tavily `extract` → MCP `firecrawl_scrape` → `scrape_url` → `fetch_url` |
| `ecommerce` | ddg | Apify actor (MCP) → `scrape_url` → `fetch_url` |
| `general` | ddg | `scrape_url` → `fetch_url` |
| any (URL given directly) | skip | per `site_type` above |
| any (3+ URLs) | skip | `scrape_urls` (parallel) |
| multi-page crawl | — | MCP `firecrawl_crawl` |
| deep research | — | MCP `firecrawl_deep_research` |

The **RULES** section of the prompt also defines the sentinel-string error protocol (see §5) and instructs the agent to return the saved file path as its final output.

**`ScraperAgent.__init__`** builds an `Agent` (from the `agents` SDK) with `name="ScraperAgent"`, `model` (default `gpt-4o-mini`, overridable via `SCRAPER_MODEL`), `instructions=_INSTRUCTIONS`, and the 9 always-on tools plus whatever `mcp_servers` were passed in. All 9 Python tools are registered unconditionally — even ones whose API key is missing — because each tool checks its own prerequisites at call time and returns `TOOL_UNAVAILABLE: ...` rather than needing to be conditionally excluded at construction time.

**`ScraperAgent.run(spec)`** does three things:
1. Serializes `spec` into the prompt and calls `Runner.run(self._agent, input=prompt, max_turns=30)` — this is the actual agent loop (LLM call → tool execution → feed result back → repeat).
2. Scans the agent's final text output for the literal string `"Saved:"` followed by a token ending in `.json` that exists on disk, then re-opens and re-parses that JSON file. This is how the Python code recovers structured output from an LLM that was asked to "return the saved path as your final output" — it's a string-matching bridge between the agent's free-text final answer and the tool's actual side effect (writing a file via `save_result`).
3. If that parsing fails or no path is found, it returns `ScrapeOutput(status="failed", errors=[...])` with the agent's raw output (truncated to 200 chars) as the error message.

### `scraper/tools/*.py` — the 9 tools

Every tool follows the same contract: **return a string (or JSON-string) describing success or failure — never raise.** This is deliberate: since the LLM only sees tool call results as text, an unhandled exception would end the whole run instead of letting the LLM try the next fallback tool per the priority table above. The sentinel prefixes are:

| Prefix | Meaning | Agent's expected reaction |
| --- | --- | --- |
| `SCRAPE_ERROR: ...` | The scrape attempt failed (network, parse, timeout) | Try the next tool in the priority order |
| `SCRAPE_EMPTY: ...` | The tool ran but got no usable content | Try the next tool |
| `SEARCH_ERROR: ...` | A search provider failed | Try the next search provider |
| `TOOL_UNAVAILABLE: ...` | Missing API key or missing optional package | Skip silently, try the next tool |
| `ERROR: ...` | Malformed input to the tool itself (e.g. bad JSON) | — |

- **`scrape_url`** (`crawl4ai_tool.py`) — headless-browser scrape via crawl4ai's `AsyncWebCrawler`. Supports `wait_for`/`js_code`/`magic` (anti-bot heuristics) passed straight from `ScrapeSpec`. Prefers `fit_markdown` → `raw_markdown` → raw string → `extracted_content`. Truncates to 20,000 chars, 30s page timeout.
- **`scrape_urls`** — same engine, parallel via `arun_many`, for 3+ URL batches. Per-URL truncation is 15,000 chars (note: different limit than `scrape_url` — an inconsistency, not a deliberate tiering).
- **`extract_structured`** — pure CSS-selector extraction via crawl4ai's `JsonCssExtractionStrategy`; no LLM call, used for known-structure table pages.
- **`pdf_extract`** (`pdf_tool.py`) — downloads the PDF (spoofed User-Agent, `verify=False`), validates it isn't actually HTML via the `%PDF` magic-byte check, tries `pdfplumber` first (tables as pipe-delimited markdown + filtered text), falls back to `pymupdf4llm` if that yields under 50 chars. Caps at 30,000 chars / 40 pages. No OCR — scanned image PDFs without a text layer will return `SCRAPE_EMPTY`.
- **`duckduckgo_search` / `tavily_search` / `firecrawl_search`** (`search_tool.py`) — three independent search backends. DDG needs no key; the other two are Python-client fallbacks used only when the corresponding MCP server isn't mounted (no key set).
- **`fetch_url`** (`fetch_tool.py`) — plain synchronous `httpx` GET, no JS rendering, explicitly documented as "last resort." Rejects binary content types and points the agent at `pdf_extract` instead.
- **`save_result`** (`output_tool.py`) — the terminal action. Parses the agent-provided JSON, injects `_meta` (schema name, ISO timestamp, `version: "1.0"`), sanitizes `schema_name` into a safe filename, writes `output/{schema}_{YYYYMMDD_HHMMSS}.json`, and returns `"Saved: <path>"` — the exact string `ScraperAgent.run()` looks for.
- **`cache.py`** — `@cached_tool` is an MD5-keyed, in-process, unbounded, no-TTL memoization decorator applied to the four idempotent/expensive tools (`scrape_url`, `extract_structured`, `pdf_extract`, `fetch_url`). Not applied to `scrape_urls`, the search tools, or `save_result` (which must always execute). Cleared only via the REPL's `/reset` command or process restart.

### `mcp_servers/mcp_manager.py` — optional capability mounting

`build_scraper_mcp_servers()` calls three builder functions and collects whichever ones return non-`None` (i.e., whichever API keys are actually set):

- **`build_tavily_mcp()`** — `MCPServerStreamableHttp` over HTTP to `https://mcp.tavily.com/mcp/?tavilyApiKey=<key>` (the key travels as a URL query parameter — worth keeping out of logs). Adds `search` + `extract`.
- **`build_firecrawl_mcp()`** — `MCPServerStdio` launching `npx -y firecrawl-mcp` with `FIRECRAWL_API_KEY` in its subprocess env. Needs Node 18+. Adds `firecrawl_scrape/search/crawl/extract/deep_research`.
- **`build_apify_mcp()`** — `MCPServerStdio` launching `npx -y @apify/mcp-server`. Note the env var translation: the project's `APIFY_API_KEY` is passed to the subprocess as `APIFY_TOKEN`, because that's the name Apify's own MCP server expects.

On Windows, `npx` is invoked via `cmd /c npx ...` rather than directly — `_npx()` branches on `sys.platform == "win32"` — because `npx` isn't directly spawnable as a subprocess target on Windows the way it is on POSIX.

## 5. Design tradeoffs worth knowing

- **Prompt-encoded routing** means changing tool priority is a prompt-engineering change, not a code change — faster to iterate, but not unit-testable in the traditional sense, and behavior can drift if the underlying LLM interprets instructions differently across model swaps.
- **String-sentinel error protocol** avoids exceptions terminating agent runs, but means tool authors must remember the convention — there's no shared exception type or `Result`-like structure enforcing it.
- **Output-path recovery via text search** (`ScraperAgent.run()` looking for `"Saved:"` + a valid `.json` path) is a fragile bridge — if the LLM paraphrases or the model doesn't echo the exact save path, the run reports `status="failed"` even though a file was actually written.
- **`verify=False`** (TLS verification disabled) is hardcoded in both `pdf_tool.py` and `fetch_tool.py`. Deliberate, likely for compatibility with self-signed/corporate-proxy certs, but worth knowing before pointing this at anything security-sensitive.
- **Truncation limits are inconsistent** across tools (20k / 15k / 30k / 15k chars) — not a tiered design, just accreted defaults.
- **No test suite** exists yet. There's no `tests/` directory, no pytest config, and no CI. This is the most significant gap for anyone planning to extend the tool set (see `docs/DEVELOPER.md`).

## 6. Output contract

Every run — regardless of which tools were used — produces `output/{schema_name}_{timestamp}.json`:

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

`data` is intentionally open-ended (`dict[str, Any]`) — the fixed part of the contract is the envelope around it, not the extracted fields themselves.
