"""
Skill loader — per-capability reference docs composed into the agent's prompt.

Each file under this package documents one capability source (crawl4ai, a
specific MCP server, or the small always-on Python tools) in depth: exact
tool names, parameters, best-for scenarios, gotchas. scraper/agent.py decides
which files to load based on which MCP servers are actually mounted, then
concatenates them onto the base instructions.

This module intentionally does NOT duplicate the site_type tool-priority
table (that stays in scraper/agent.py's _BASE_INSTRUCTIONS, CLAUDE.md, and
docs/ARCHITECTURE.md) — skills own per-capability depth, not tool ordering.
"""

from __future__ import annotations

from pathlib import Path

_SKILLS_DIR = Path(__file__).parent
_cache: dict[str, str] = {}


def load_skill(name: str) -> str:
    """
    Load a skill doc by name (without .md extension), e.g. load_skill("crawl4ai").
    Cached in-process — skill content never changes at runtime.
    """
    if name not in _cache:
        _cache[name] = (_SKILLS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
    return _cache[name]
