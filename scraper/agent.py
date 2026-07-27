"""
ScraperAgent — a universal, configurable web scraping agent.

Usage
-----
from scraper.agent import ScraperAgent
from scraper.spec import ScrapeSpec
from mcp_servers import build_scraper_mcp_servers

agent = ScraperAgent(mcp_servers=build_scraper_mcp_servers())
result = await agent.run(ScrapeSpec(
    target="https://example.com/report.pdf",
    site_type="pdf",
    extract_fields={"revenue": "number", "npat": "number"},
    schema_name="financials",
))
print(result.status, result.data)
"""

from __future__ import annotations

import json
import logging
import os
import time

from agents import Agent, MultiProvider, RunConfig, Runner
from agents.items import ToolCallItem, ToolCallOutputItem
from scraper.spec import ScrapeSpec, ScrapeOutput
from scraper.skills import load_skill
from scraper.tools import (
    scrape_url, scrape_urls, extract_structured, crawl_paginated,
    pdf_extract,
    duckduckgo_search, tavily_search, firecrawl_search,
    fetch_url,
    save_result,
)

log = logging.getLogger(__name__)

# Skill files loaded unconditionally — the always-on Python tools.
_ALWAYS_ON_SKILLS = ["crawl4ai", "search_and_fetch"]

# Skill files loaded only when the matching MCP server is actually mounted.
# Keyed by MCPServer.name as set in mcp_servers/mcp_manager.py.
_MCP_SKILLS = {
    "tavily": "tavily_mcp",
    "firecrawl": "firecrawl_mcp",
    "apify": "apify_mcp",
}

# Some providers (Groq's "groq/compound", OpenRouter's "openrouter/openai/gpt-4o",
# etc.) use "/" as part of the literal model ID, not as a routing prefix. The
# SDK's default MultiProvider raises UserError on any "prefix/..." string it
# doesn't recognize as one of its own routing schemes (litellm/, openai/).
# unknown_prefix_mode="model_id" passes such strings through as-is to the
# already-configured OpenAI-compatible client (see main.py::_setup_client)
# instead of erroring — this is the SDK's documented escape hatch for exactly
# this case.
#
# openai_use_responses=False forces the classic Chat Completions API
# (POST /chat/completions) instead of the SDK's default — OpenAI's newer
# Responses API (POST /responses). The SDK defaults use_responses=True
# globally. Chat Completions is the far more universal, battle-tested
# standard across OpenAI-compatible providers; Responses is newer and,
# even where a provider claims support, its tool-calling compatibility layer
# has proven unreliable in practice here (malformed "<function=...>" text
# artifacts leaking through instead of clean structured tool calls, observed
# across multiple different models on Groq). Chat Completions' tool-calling
# is what virtually every provider gets right first and tests most.
_MODEL_PROVIDER = MultiProvider(unknown_prefix_mode="model_id", openai_use_responses=False)

_BASE_INSTRUCTIONS = """
You are the ScraperAgent — a universal web scraper that extracts structured data
from websites and PDFs and saves it as a JSON file.

You will receive a SCRAPE SPEC block describing the job. Follow the phases below.

════════════════════════════════════════════════
PHASE 0 — READ THE SPEC
════════════════════════════════════════════════
Parse the SCRAPE SPEC JSON. Note:
  • target         — URL or search query
  • site_type      — financial | news | ecommerce | pdf | table | general
  • extract_fields — {field_name: type} — what to pull out (MAY BE EMPTY, see below)
  • extraction_hint — optional human hint / plain-language goal
  • wait_for / js_code — optional browser control for scrape_url
  • magic          — anti-bot mode for scrape_url
  • output_dir     — where to save

A regular user typically only provides `target` and, optionally,
`extraction_hint` in their own words (e.g. "get me the pricing tiers").
Everything else is a hint for YOU to refine, not a literal instruction to
follow blindly:
  • If site_type is "general" (the default), that does NOT mean the page
    actually is general-purpose. Look at the URL/domain and the content you
    scrape and mentally reclassify it (financial/news/ecommerce/pdf/table)
    if it clearly fits one — then follow that row in the PHASE 2 table below
    instead of the general-purpose one.
  • If extract_fields is empty, decide what to extract yourself — see
    PHASE 3 for how.

════════════════════════════════════════════════
PHASE 1 — ACQUIRE CONTENT (search phase)
════════════════════════════════════════════════
If target starts with "http":
  → Skip to PHASE 2 with that URL directly.

If target is a search query:
  → Try search tools in this order, stop when you have 2-3 good URLs:
     MCP tools (if mounted — see TAVILY MCP / FIRECRAWL MCP skills below for full detail):
       1. tavily `search`          ← best for financial/news — also try `extract` for direct URL content
       2. firecrawl `firecrawl_search` ← crawl + search combined
     Python tools (always available — see SEARCH & FETCH skill below):
       3. tavily_search            ← Python client fallback if Tavily MCP absent
       4. duckduckgo_search        ← always available, no key needed
       5. firecrawl_search         ← Python client fallback if Firecrawl MCP absent

════════════════════════════════════════════════
PHASE 2 — SCRAPE CONTENT
════════════════════════════════════════════════
Choose tools based on site_type and URL. MCP tools are preferred when available.
Full parameters and usage detail for every tool named below are in the skill
sections at the end of this prompt — this table only sets the TRY ORDER.

  PDF URLs (.pdf in URL, or site_type="pdf"):
    1. pdf_extract(url)              ← always try first — tables + text
    2. firecrawl `firecrawl_scrape`  ← if MCP mounted and pdf_extract fails
    3. scrape_url(url)               ← crawl4ai fallback
    4. fetch_url(url)                ← last resort

  Table-heavy pages (site_type="table"):
    1. firecrawl `firecrawl_extract` ← LLM-guided structured extraction (MCP)
    2. extract_structured(url, css_schema_json) ← CSS selector extraction (crawl4ai)
    3. scrape_url(url, css_selector=...) ← fallback, scope with css_selector if known

  Multi-page site crawl (many links to follow):
    1. firecrawl `firecrawl_crawl`   ← follows links across the site (MCP)
    2. scrape_urls(urls_json)         ← parallel batch via crawl4ai

  PAGINATED LISTINGS — check this on every scrape, not just when asked:
    After your first scrape_url call, check whether the content shows
    pagination (page numbers, "Next"/"Prev" links, "Page X of Y", numbered
    links like 1 2 3 4 5). If it does AND the user's goal implies wanting
    the complete set (e.g. "list all X", "every Y", extract_fields
    suggesting a list of many items) — don't stop at page 1:
      1. firecrawl `firecrawl_crawl`  ← if Firecrawl MCP is mounted, prefer
         this — it follows pagination/links itself, no pattern needed.
      2. crawl_paginated(start_url, max_pages, url_pattern)  ← otherwise,
         THIS is the primary tool. It follows the real pagination links
         deterministically (crawl4ai's own crawl engine) instead of you
         constructing URLs yourself. Look at the actual pagination link
         hrefs on the first page and pass a glob matching them as
         url_pattern (e.g. '*page=*' or '*/page/*'), and set max_pages to
         the real total page count you saw (e.g. "Page 1 of 5" → 5).
         Returns one JSON object per page — merge every page's items into
         one combined `data` list before saving.
      3. Only if crawl_paginated errors or crawl4ai is unavailable: fall
         back to manually building page URLs yourself and calling
         scrape_urls(urls_json) with all of them — this is a last resort,
         not the default path.
    If you can't confidently identify the pagination link pattern, still
    call crawl_paginated with just max_pages set (it will same-domain-scope
    the crawl as a safety net) rather than giving up — but if that clearly
    still isn't catching the right pages, add a note to `errors` saying
    pagination was detected but not fully followed. Don't silently
    under-deliver without saying so.

  Deep research across many pages:
    1. firecrawl `firecrawl_deep_research` ← multi-step AI research (MCP)

  Specific known platforms (social, e-commerce, SERP, maps, jobs, reviews):
    1. Apify MCP (if mounted) ← see APIFY MCP skill below — it's a DISCOVERY
       workflow (search-actors → fetch-actor-details → call-actor), not a
       fixed list of tools. Use it when the target is a known platform a
       generic scraper struggles with.
    If Apify MCP is NOT mounted and the target is a login-gated / bot-hostile
    platform (LinkedIn, Instagram, most job boards behind a sign-in wall,
    etc.): do NOT attempt complex js_code interactions (clicking buttons,
    triggering search) to work around the login wall — this rarely works
    (you'll just see the login page) and risks generating malformed tool
    calls (see the js_code RULE below). Instead: try one plain scrape_url or
    fetch_url call with no js_code, and if the content is clearly a login
    wall or near-empty, report status="partial"/"failed" with an error
    noting the platform requires APIFY_API_KEY (or a logged-in session) to
    scrape properly — don't keep escalating to more elaborate JS attempts.

  Regular web pages (site_type="general", "news", "ecommerce", "financial"):
    1. tavily `extract`              ← direct URL content pull (Tavily MCP)
    2. firecrawl `firecrawl_scrape`  ← high quality (Firecrawl MCP)
    3. scrape_url(url, wait_for=..., js_code=..., magic=..., remove_popups=...)  ← crawl4ai
    4. fetch_url(url)                ← plain HTTP, last resort

  3+ URLs at once:
    → Use scrape_urls(urls_json) for parallel crawl4ai fetching.

════════════════════════════════════════════════
PHASE 3 — EXTRACT FIELDS
════════════════════════════════════════════════
If extract_fields is NOT empty:
  • Extract every field listed. Use extraction_hint if provided — it tells
    you where to look. If a field cannot be found, set its value to null —
    never invent data. Match the declared type: number → numeric,
    string → text, list → array.

If extract_fields IS empty — decide yourself what belongs in `data`:
  • If extraction_hint is provided (the user's plain-language goal, e.g.
    "get me the pricing tiers" or "summarize the roadmap topics"), derive
    sensible field names/types from it and extract those.
  • If extraction_hint is ALSO empty, produce a general-purpose summary:
    at minimum `title` (string) and `summary` (string, a few sentences).
    Add `key_points` (list of strings) and any other field that's obviously
    useful for this specific page (e.g. `pricing` for a pricing page,
    `topics` for a roadmap/course page) — invent reasonable field names,
    there's no fixed schema to match.
  • Either way, `data`'s keys should reflect what you actually decided to
    extract — don't leave it empty just because extract_fields was empty.

════════════════════════════════════════════════
PHASE 4 — SAVE RESULT
════════════════════════════════════════════════
Call save_result ONCE with this exact JSON envelope:

{
  "status": "success",          // "success" | "partial" | "failed"
  "data": {
    "field_name": <value>,      // one key per extract_fields entry
    ...
  },
  "sources": ["url1", "url2"],  // every URL scraped
  "tools_used": ["scrape_url", "firecrawl_scrape"],
  "errors": [],                 // any non-fatal errors encountered
  "raw_text": null              // null unless spec.include_raw_text=true
}

Use "partial" if some fields were found but others are null.
Use "failed" only if no content could be scraped at all.

Pass schema_name and output_dir from the spec.

════════════════════════════════════════════════
RULES
════════════════════════════════════════════════
• Never invent or estimate field values — null is always correct for missing data.
• SCRAPE_ERROR / SCRAPE_EMPTY prefixes mean that tool failed — try the next one.
• TOOL_UNAVAILABLE means the tool is not configured — skip it silently.
• EVERY tool call must include ONLY the parameters that specific tool declares
  in its own schema — never copy fields from the SCRAPE SPEC block into a tool
  call just because the names look similar or nearby. For example, the SCRAPE
  SPEC has extraction_hint/include_raw_text/use_session/schema_name/output_dir
  fields, but scrape_url does NOT accept any of those as parameters — passing
  them will be rejected. Read each tool's own parameter list (in its skill
  doc below) before calling it, don't assume it mirrors the spec.
• Keep scrape_url's js_code SIMPLE — a short, single expression, one quote
  style only (prefer no nested/escaped quotes at all, e.g. use a CSS selector
  with no quoted attribute values, or restructure to avoid mixing ' and "
  inside the same string). Complex js_code with nested/escaped quotes has
  caused tool-call generation itself to fail outright (not a schema error —
  the call never forms at all) on some models. If a scrape_url call with
  js_code fails or errors for any reason, retry ONCE with js_code omitted
  before moving to the next tool in the priority order — don't retry with
  more elaborate js_code.
• MCP tool names come from the server (firecrawl_scrape, search, extract, etc.) —
  they appear automatically in your tool list when the MCP server is mounted.
• Call save_result exactly once at the end of every run.
• Return the file path from save_result as your final output.
• Below this rules section are SKILL sections — one per capability source
  that's actually active for this run. Read them for exact tool names,
  parameters, and gotchas before calling a tool you haven't used yet.
"""


def _compose_instructions(mcp_servers: list) -> str:
    """
    Build the final system prompt: base phase/rules skeleton + skill docs.
    Always-on skills (crawl4ai, search/fetch) are included unconditionally;
    MCP skills are included only for servers actually present in
    mcp_servers, so an agent with no Tavily key doesn't carry Tavily
    documentation (and token cost) in its prompt.
    """
    parts = [_BASE_INSTRUCTIONS]

    for name in _ALWAYS_ON_SKILLS:
        parts.append(load_skill(name))

    mounted = {getattr(server, "name", None) for server in mcp_servers}
    for server_name, skill_name in _MCP_SKILLS.items():
        if server_name in mounted:
            parts.append(load_skill(skill_name))

    return "\n\n".join(parts)


class ScraperAgent:
    """
    Universal web scraping agent.

    Parameters
    ----------
    model : str
        LLM model. Defaults to SCRAPER_MODEL env var or "gpt-4o-mini".
    mcp_servers : list
        MCP server instances (from mcp_servers.build_scraper_mcp_servers()).
        When present, the agent gains firecrawl_crawl, firecrawl_deep_research,
        firecrawl_extract, tavily extract, and Apify's actor-discovery tools
        (search-actors/call-actor/etc.) — each mounted server's .name also
        activates its matching skill doc in the prompt (see scraper/skills/).
    extra_tools : list
        Additional @function_tool functions to inject (project-specific tools).
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: list | None = None,
        extra_tools: list | None = None,
    ) -> None:
        self.model = model or os.getenv("SCRAPER_MODEL", "gpt-4o-mini")

        all_tools = [
            # Crawl4ai — full feature set
            scrape_url,
            scrape_urls,
            extract_structured,
            crawl_paginated,
            # PDF
            pdf_extract,
            # Search (Python clients — fallback when MCP not mounted)
            duckduckgo_search,
            tavily_search,
            firecrawl_search,
            # Fallback HTTP
            fetch_url,
            # Output
            save_result,
        ]
        if extra_tools:
            all_tools.extend(extra_tools)

        mcp_servers = mcp_servers or []
        self._agent = Agent(
            name="ScraperAgent",
            model=self.model,
            instructions=_compose_instructions(mcp_servers),
            tools=all_tools,
            mcp_servers=mcp_servers,
        )

    async def run(self, spec: ScrapeSpec) -> ScrapeOutput:
        """
        Run a scraping job from a ScrapeSpec and return a ScrapeOutput.

        Parameters
        ----------
        spec : ScrapeSpec
            The scraping job specification.

        Returns
        -------
        ScrapeOutput
            Parsed result with .status, .data, .sources, .tools_used, .errors.
        """
        prompt = f"SCRAPE SPEC:\n{spec.to_prompt_block()}"
        log.info("ScraperAgent.run — target=%r schema=%r", spec.target, spec.schema_name)

        start = time.monotonic()
        result = await Runner.run(
            self._agent,
            input=prompt,
            max_turns=30,
            run_config=RunConfig(model_provider=_MODEL_PROVIDER),
        )
        duration = round(time.monotonic() - start, 2)

        output_str = str(result.final_output or "")
        log.info("ScraperAgent finished in %.1fs — output: %s", duration, output_str[:120])

        # Primary path: read save_result's actual return value from the tool-call
        # trace (correlated by call_id), not the model's paraphrased final chat
        # message. The model's last message is free text and isn't guaranteed to
        # repeat the exact "Saved: <path>" string even when the save succeeded —
        # relying on that was the previous (fragile) approach.
        save_result_output: str | None = None
        outputs_by_call_id = {
            item.call_id: item.output
            for item in result.new_items
            if isinstance(item, ToolCallOutputItem)
        }
        for item in result.new_items:
            if isinstance(item, ToolCallItem) and item.tool_name == "save_result":
                save_result_output = outputs_by_call_id.get(item.call_id)
                break

        saved_path = None
        if save_result_output and str(save_result_output).startswith("Saved:"):
            candidate = str(save_result_output).split("Saved:", 1)[1].strip()
            if os.path.exists(candidate):
                saved_path = candidate

        # Fallback: scan the model's final text in case the tool-call trace
        # couldn't be correlated for some reason (e.g. a future SDK change).
        if not saved_path and "Saved:" in output_str:
            for part in output_str.split():
                if part.endswith(".json") and os.path.exists(part):
                    saved_path = part
                    break

        if saved_path:
            try:
                with open(saved_path, encoding="utf-8") as f:
                    raw = json.load(f)
                return ScrapeOutput(
                    meta={
                        **raw.get("_meta", {}),
                        "duration_seconds": duration,
                        "output_path": saved_path,
                    },
                    status=raw.get("status", "failed"),
                    data=raw.get("data", {}),
                    sources=raw.get("sources", []),
                    tools_used=raw.get("tools_used", []),
                    errors=raw.get("errors", []),
                    raw_text=raw.get("raw_text") if spec.include_raw_text else None,
                )
            except Exception as e:
                log.error("Could not parse saved result from %s: %s", saved_path, e)

        return ScrapeOutput(
            meta={"duration_seconds": duration, "agent_output": output_str[:500]},
            status="failed",
            errors=[f"Could not locate saved output file. Agent said: {output_str[:200]}"],
        )
