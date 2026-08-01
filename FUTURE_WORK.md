# scraper-agent — Future Work

> _Last updated: August 2026_

## 1. Test Suite & CI

Biggest gap — there are no tests and no CI. Natural seams:
- **Unit tests**: `_parse_fields` in `main.py` (field-spec parsing), `save_result` filename sanitization, `_default_schema_name` slugging
- **Unit tests**: `_compose_instructions` / skills composition (with/without MCP keys)
- **Unit tests**: `@cached_tool` MD5 keying + `clear_cache`
- **Unit tests** (mock `Runner.run`): `ScraperAgent.run()` output-path recovery from the tool-call trace
- **Integration tests** behind a marker that requires real API keys (crawl4ai + at least one search provider)

## 2. Doc Debt Cleanup (stale docs)

- `docs/DEVELOPER.md` says "No .gitignore exists yet" — a `.gitignore` exists since commit c38e2d4
- `docs/DEVELOPER.md` says `_parse_fields` is duplicated inline in `_repl()` — the REPL now only prompts for target + hint, no field parsing
- `CLAUDE.md` and `docs/ARCHITECTURE.md` §4 still describe the REPL prompting for `site_type` / `schema_name` / `fields` / `hint` each turn — stale; §8 is correct (target + optional goal)

## 3. Cache Bounding

`@cached_tool` is unbounded with no TTL — fine for the CLI, but must get size/TTL/eviction before embedding `ScraperAgent` in a long-lived service.

## 4. TLS Verification

`verify=False` is hardcoded in `scraper/tools/pdf_tool.py` and `scraper/tools/fetch_tool.py` (deliberate, for self-signed/proxy compat). Revisit before any security-sensitive deployment — make it configurable, not constant.

## 5. Unify Truncation Limits

Per-tool family limits differ and can surprise: crawl4ai 20k chars (`MAX_CONTENT_CHARS`), `pdf_extract` 30k chars / 40 pages, `fetch_url` 15k. Consider a single configurable budget policy.

## 6. Packaging Fix

`pyproject.toml` packages only `scraper*` / `mcp_servers*` but the console script is `main:main` at the repo root — `pip install .` from elsewhere likely lacks `main.py`. Add `py-modules = ["main"]` to `[tool.setuptools]`.

## 7. License

No LICENSE file specified yet — pick one (MIT is the common choice for this kind of OSS tool).

## 8. Log Hygiene for Tavily MCP Key

The Tavily MCP key travels as a URL query parameter (`?tavilyApiKey=...`) — ensure it never lands in logs when debugging MCP subprocesses.

## 9. Apify Key Alias

`build_apify_mcp()` renames `APIFY_API_KEY` → `APIFY_TOKEN` for the subprocess — a recurring debugging trap. Consider accepting both names inside the server, or documenting the rename at the .env.example level.
