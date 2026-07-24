"""
scraper-agent CLI — interactive REPL and programmatic entry point.

Usage
-----
  python main.py                     # interactive prompt
  python main.py "https://example.com" --schema homepage --fields "title:string,h1:string"
  python main.py "Apple revenue 2024" --site-type news --fields "headline:string,date:string"

Environment
-----------
  Required: PROVIDER + matching API key (see .env.example)
  Optional: TAVILY_API_KEY, FIRECRAWL_API_KEY, SCRAPER_MODEL
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.prompt import Prompt

load_dotenv()

console = Console()

# Route scraper.* logs through Rich
_handler = RichHandler(console=console, show_time=False, show_path=False, markup=True)
_scraper_logger = logging.getLogger("scraper")
_scraper_logger.addHandler(_handler)
_scraper_logger.setLevel(logging.INFO)
_scraper_logger.propagate = False


def _setup_client() -> None:
    """Configure the OpenAI-compatible client from PROVIDER env var."""
    provider = os.getenv("PROVIDER", "openai").lower().strip()
    api_key = os.getenv("API_KEY", "").strip()

    base_urls: dict[str, str] = {
        "openai":     "https://api.openai.com/v1",
        "groq":       "https://api.groq.com/openai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "gemini":     "https://generativelanguage.googleapis.com/v1beta/openai",
        "ollama":     "http://localhost:11434/v1",
        "together":   "https://api.together.xyz/v1",
        "deepseek":   "https://api.deepseek.com/v1",
        "nvidia":     "https://integrate.api.nvidia.com/v1",
        "huggingface":"https://api-inference.huggingface.co/v1",
        "cerebras":   "https://api.cerebras.ai/v1",
    }

    if not api_key:
        key_vars = {
            "openai": "OPENAI_API_KEY", "groq": "GROQ_API_KEY",
            "openrouter": "OPENROUTER_API_KEY", "gemini": "GEMINI_API_KEY",
            "together": "TOGETHER_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
            "nvidia": "NVIDIA_API_KEY", "huggingface": "HUGGINGFACE_API_KEY",
            "cerebras": "CEREBRAS_API_KEY",
        }
        api_key = os.getenv(key_vars.get(provider, ""), "").strip()

    if not api_key and provider != "ollama":
        console.print(f"[red]No API key for provider '{provider}'. Set API_KEY or the provider-specific key in .env[/red]")
        sys.exit(1)

    from openai import AsyncOpenAI
    import agents

    base_url = base_urls.get(provider)
    client = AsyncOpenAI(api_key=api_key or "ollama", base_url=base_url)
    agents.set_default_openai_client(client)

    if provider != "openai":
        agents.set_tracing_disabled(True)


async def _run_once(
    target: str,
    *,
    site_type: str = "general",
    fields: dict[str, str] | None = None,
    schema_name: str = "scraped",
    extraction_hint: str = "",
    output_dir: str = "output",
    include_raw: bool = False,
) -> None:
    from scraper import ScraperAgent, ScrapeSpec

    spec = ScrapeSpec(
        target=target,
        site_type=site_type,
        extract_fields=fields or {},
        schema_name=schema_name,
        extraction_hint=extraction_hint,
        output_dir=output_dir,
        include_raw_text=include_raw,
    )

    agent = ScraperAgent()
    console.print(Panel(spec.to_prompt_block(), title="[bold]Scrape Job[/bold]", expand=False))

    result = await agent.run(spec)

    status_color = {"success": "green", "partial": "yellow", "failed": "red"}.get(result.status, "white")
    console.print(f"\n[{status_color}]Status: {result.status}[/{status_color}]")

    if result.data:
        console.print("\n[bold]Extracted Data:[/bold]")
        console.print_json(json.dumps(result.data, indent=2, ensure_ascii=False))

    if result.errors:
        console.print("\n[yellow]Errors:[/yellow]")
        for e in result.errors:
            console.print(f"  • {e}")

    if result.meta.get("output_path"):
        console.print(f"\n[dim]Saved → {result.meta['output_path']}[/dim]")


async def _repl() -> None:
    from scraper import ScraperAgent, ScrapeSpec

    console.print(Panel(
        "[bold]scraper-agent[/bold] — Universal Web Scraper\n"
        "Type a URL or search query, then follow the prompts.\n"
        "Commands: [dim]/reset[/dim] clear cache  [dim]/quit[/dim] exit",
        expand=False,
    ))

    agent = ScraperAgent()

    while True:
        try:
            target = Prompt.ask("\n[bold green]>[/bold green] Target (URL or query)")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Bye.[/dim]")
            break

        if target.strip().lower() in ("/quit", "/exit", "quit", "exit"):
            break

        if target.strip().lower() == "/reset":
            from scraper.tools.cache import clear_cache
            clear_cache()
            console.print("[dim]Cache cleared.[/dim]")
            continue

        site_type = Prompt.ask(
            "Site type",
            choices=["general", "financial", "news", "ecommerce", "pdf", "table"],
            default="general",
        )
        schema_name = Prompt.ask("Schema name (for output filename)", default="scraped")
        fields_raw = Prompt.ask(
            "Fields to extract (field:type, comma-separated, or leave blank)",
            default="",
        )
        hint = Prompt.ask("Extraction hint (optional)", default="")

        fields: dict[str, str] = {}
        if fields_raw.strip():
            for pair in fields_raw.split(","):
                pair = pair.strip()
                if ":" in pair:
                    k, v = pair.split(":", 1)
                    fields[k.strip()] = v.strip()
                else:
                    fields[pair] = "string"

        spec = ScrapeSpec(
            target=target,
            site_type=site_type,
            extract_fields=fields,
            schema_name=schema_name,
            extraction_hint=hint,
            output_dir="output",
        )

        console.print()
        try:
            result = await agent.run(spec)
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")
            continue

        status_color = {"success": "green", "partial": "yellow", "failed": "red"}.get(result.status, "white")
        console.print(f"[{status_color}]Status: {result.status}[/{status_color}]")

        if result.data:
            console.print_json(json.dumps(result.data, indent=2, ensure_ascii=False))

        if result.errors:
            for e in result.errors:
                console.print(f"  [yellow]• {e}[/yellow]")

        if result.meta.get("output_path"):
            console.print(f"[dim]Saved → {result.meta['output_path']}[/dim]")


def _parse_fields(raw: str) -> dict[str, str]:
    """Parse "title:string,price:number" into {"title": "string", "price": "number"}."""
    out: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if ":" in pair:
            k, v = pair.split(":", 1)
            out[k.strip()] = v.strip()
        else:
            out[pair] = "string"
    return out


def main() -> None:
    _setup_client()

    parser = argparse.ArgumentParser(
        prog="scraper-agent",
        description="Universal AI web scraper",
    )
    parser.add_argument("target", nargs="?", help="URL or search query (omit for interactive mode)")
    parser.add_argument("--schema", default="scraped", help="Schema name for the output file")
    parser.add_argument("--site-type", default="general",
                        choices=["general", "financial", "news", "ecommerce", "pdf", "table"])
    parser.add_argument("--fields", default="",
                        help="Comma-separated field:type pairs, e.g. 'title:string,price:number'")
    parser.add_argument("--hint", default="", help="Extraction hint passed to the agent")
    parser.add_argument("--output-dir", default="output", help="Output directory for JSON results")
    parser.add_argument("--raw", action="store_true", help="Include full raw scraped text in output")

    args = parser.parse_args()

    if args.target:
        fields = _parse_fields(args.fields)
        asyncio.run(_run_once(
            args.target,
            site_type=args.site_type,
            fields=fields,
            schema_name=args.schema,
            extraction_hint=args.hint,
            output_dir=args.output_dir,
            include_raw=args.raw,
        ))
    else:
        asyncio.run(_repl())


if __name__ == "__main__":
    main()
