# scraper-agent

A universal, AI-driven web scraping agent. Point it at a URL, a PDF, or a plain-English search query and it figures out — on its own, at runtime — which tool to use, in what order, and how to fall back when one fails, then hands you back a fixed-shape JSON result.

It's built on the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python), works with **any OpenAI-compatible LLM provider** (OpenAI, Groq, OpenRouter, Gemini, Ollama, Together, DeepSeek, NVIDIA, HuggingFace, Cerebras), and layers in optional [MCP](https://modelcontextprotocol.io/) servers (Tavily, Firecrawl, Apify) when you have API keys for them.

## Why

Most scrapers are pipelines: fetch → parse → map fields, hardcoded per site. This one is a single LLM agent with a toolbox — the routing logic ("try crawl4ai, fall back to plain fetch, use pdfplumber for PDFs, use Apify for known e-commerce platforms...") lives in the agent's system prompt, not in Python `if/else` branches. Add a new tool or MCP server and the agent can start using it without a rewrite of the control flow.

## Features

- **Just give it a URL** — you don't need to know what "site_type" or "extract_fields" mean. Give a URL/query and, optionally, a plain-language goal ("get me the pricing tiers") — the agent classifies the page and decides what's worth extracting on its own. Manual overrides (`--site-type`, `--fields`, `--schema`) are still there for scripted/advanced use.
- **One agent, many tools** — browser-rendered scraping (crawl4ai), plain HTTP fetch, PDF extraction, CSS-selector table extraction, and three search backends, always available.
- **Optional MCP servers** — mount Tavily (search + extract), Firecrawl (scrape/crawl/deep-research/extract), and Apify (actor discovery — 3,000+ site-specific scrapers) just by setting an API key.
- **Skills layer** — each tool/MCP server has a dedicated reference doc (`scraper/skills/`) giving the agent real depth on parameters and gotchas, not just a one-line mention — loaded only for integrations you've actually configured.
- **Fixed output schema** — every run produces the same JSON envelope (`status`, `data`, `sources`, `tools_used`, `errors`), regardless of which tools the agent chose.
- **10 LLM providers** — swap providers with one env var; anything OpenAI-compatible works, including local Ollama.
- **CLI and REPL** — one-shot `python main.py "<url or query>"` or an interactive session that reuses the same agent across turns.

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (use `source .venv/bin/activate` on macOS/Linux)
pip install -r requirements.txt
playwright install chromium     # required — crawl4ai's browser engine, not installed by pip alone
copy .env.example .env          # then fill in PROVIDER + an API key
```

`crawl4ai` (line in `requirements.txt`) pulls in the `playwright` Python package via pip, but Playwright's actual browser binary is a separate ~300MB download that `pip install` never triggers automatically. Skip this step and `scrape_url` will fail with `BrowserType.launch: Executable doesn't exist` and silently fall back to `fetch_url` (plain HTTP, no JavaScript rendering) — which returns much thinner content on any JS-rendered site.

Optional extras for Tavily/Firecrawl Python-client fallbacks (not required for the MCP versions):

```bash
pip install tavily-python firecrawl-py
```

Run it:

```bash
python main.py                              # interactive REPL — just a URL/query + optional goal
python main.py "https://example.com/report.pdf"   # simplest form — agent infers everything else
python main.py "https://example.com/report.pdf" --schema report --fields "revenue:number,npat:number"  # manual override
```

## Example

`python main.py "https://news.ycombinator.com" --hint "top 5 stories with points"` would work fine on its own — the agent infers `site_type="news"` and sensible fields. Here's the same job with every option pinned manually, for scripted/reproducible use:

```bash
python main.py "https://news.ycombinator.com" \
  --site-type news \
  --schema hn_frontpage \
  --fields "title:string,points:integer,url:string" \
  --hint "Extract the top 5 stories only"
```

This writes `output/hn_frontpage_<timestamp>.json`:

```json
{
  "_meta": { "schema_name": "hn_frontpage", "saved_at": "...", "version": "1.0" },
  "status": "success",
  "data": { "...": "..." },
  "sources": ["https://news.ycombinator.com"],
  "tools_used": ["scrape_url", "save_result"],
  "errors": [],
  "raw_text": null
}
```

## How it works, in short

`main.py` builds a `ScrapeSpec` (your target + desired fields), hands it to a single `Agent` (`scraper/agent.py`) equipped with 9 always-on Python tools plus any MCP servers your `.env` unlocks. The agent's system prompt encodes a 4-phase plan — search (if needed) → scrape (tool order depends on `site_type`) → extract fields → save — and every tool reports failures as plain strings (`SCRAPE_ERROR: ...`, `TOOL_UNAVAILABLE: ...`) instead of raising, so the LLM can read the failure and try the next tool itself.

For the full design rationale, tool-by-tool breakdown, and data flow, see **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**. For contributing, extending, and local dev workflow, see **[docs/DEVELOPER.md](docs/DEVELOPER.md)**.

## Configuration

| Env Var | Default | Purpose |
| --- | --- | --- |
| `PROVIDER` | `openai` | LLM provider — one of `openai, groq, openrouter, gemini, ollama, together, deepseek, nvidia, huggingface, cerebras` |
| `API_KEY` | — | Universal API key (overrides provider-specific key) |
| `SCRAPER_MODEL` | `gpt-4o-mini` | Model passed to the agent |
| `TAVILY_API_KEY` | — | Enables Tavily MCP (`search` + `extract`) and the `tavily_search` fallback tool |
| `FIRECRAWL_API_KEY` | — | Enables Firecrawl MCP (`firecrawl_scrape/crawl/extract/deep_research`) and the `firecrawl_search` fallback tool |
| `APIFY_API_KEY` | — | Enables Apify MCP (3,000+ pre-built scrapers) |

See `.env.example` for the full list including provider-specific key names.

## Requirements

- Python 3.11+
- Node.js 18+ (only if you want the Firecrawl or Apify MCP servers — they run via `npx`)

## Project layout

```text
main.py                          CLI / REPL entry point
scraper/
  agent.py                       ScraperAgent — the Agent + system prompt
  spec.py                        ScrapeSpec / ScrapeOutput models
  tools/                         crawl4ai, pdf, search, fetch, output, cache
mcp_servers/
  mcp_manager.py                 builds Tavily/Firecrawl/Apify MCP servers
```

## License

Not yet specified.
