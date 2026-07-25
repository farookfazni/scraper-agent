## SKILL: search, PDF, and fallback tools (always available, Python)

### duckduckgo_search(query, max_results=5)
No API key needed, always works. Your default search tool when no MCP search
server is mounted and no Tavily/Firecrawl key is configured. Returns
`[{url, title, snippet}]`.

### tavily_search(query, max_results=5)
Python-client fallback — only useful if `TAVILY_API_KEY` is set but the
Tavily MCP server isn't mounted for some reason. If the Tavily MCP server IS
mounted, prefer its `tavily-search` tool instead (see TAVILY MCP skill) — it
has more capability (search depth control, direct extract). Fixed at
`search_depth="advanced"`. Returns `TOOL_UNAVAILABLE` if the key is missing.

### firecrawl_search(query, max_results=5)
Same fallback relationship to the Firecrawl MCP server — prefer
`firecrawl_search` via MCP when mounted (see FIRECRAWL MCP skill), use this
Python version only as a backstop. Returns `TOOL_UNAVAILABLE` if
`FIRECRAWL_API_KEY` is missing.

### pdf_extract(url)
Always try first for `site_type="pdf"` or any `.pdf` URL. Downloads the file,
tries `pdfplumber` first (extracts tables as pipe-delimited markdown rows
plus filtered body text), falls back to `pymupdf4llm` if that yields under 50
chars. Caps at 30,000 chars / first 40 pages. No OCR — a scanned PDF with no
text layer will return `SCRAPE_EMPTY: ... may be a scanned image without OCR`
— at that point stop trying PDF tools and fall back to `scrape_url`/
`fetch_url` on the same URL (sometimes yields a viewer page with text) or
report the field as unavailable.

### fetch_url(url)
Plain synchronous HTTP GET, no JavaScript rendering. LAST RESORT ONLY — use
after `scrape_url` (crawl4ai) has failed or is unavailable, since most modern
sites need JS rendering to show real content. Rejects binary content types
(pdf/zip/octet-stream) and tells you to use `pdf_extract` instead. Caps at
15,000 chars, no truncation marker.

### save_result(result_json, schema_name, output_dir="output")
Terminal action — call exactly ONCE per job, at the very end, with the full
JSON envelope (status/data/sources/tools_used/errors/raw_text). Writes
`output/{schema_name}_{timestamp}.json` and returns `"Saved: <path>"`. This
exact return string is what the caller (ScraperAgent.run) parses to locate
your output file — always return this string as your final answer after
calling save_result.
