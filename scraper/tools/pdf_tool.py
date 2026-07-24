"""
PDF extraction tool — downloads a PDF and extracts tables + text.

Priority:
  1. pdfplumber  — tables (pipe-delimited markdown) + plain text
  2. pymupdf4llm — markdown via PyMuPDF (better for scanned/older PDFs)
"""

from __future__ import annotations

import logging
import os
import tempfile

from agents import function_tool
from scraper.tools.cache import cached_tool

log = logging.getLogger(__name__)

CHAR_LIMIT = 30_000
MAX_PAGES  = 40


@function_tool
@cached_tool
async def pdf_extract(url: str) -> str:
    """
    Download a PDF from a URL and extract all tables and text.
    Use this first for any URL ending in .pdf or known to serve a PDF.
    Free — no API key required. Extracts up to 40 pages / 30 000 chars.

    Args:
        url: Direct URL to the PDF file.

    Returns:
        Extracted content as markdown text, or a SCRAPE_ERROR/SCRAPE_EMPTY string.
    """
    try:
        import httpx
    except ImportError:
        return "TOOL_UNAVAILABLE: httpx not installed — pip install httpx"

    try:
        import pdfplumber
    except ImportError:
        return "TOOL_UNAVAILABLE: pdfplumber not installed — pip install pdfplumber"

    # Download
    log.info("pdf_extract downloading %s", url)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30, verify=False) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return f"SCRAPE_ERROR: pdf_extract — HTTP {resp.status_code}"
        if "html" in resp.headers.get("content-type", "") and b"%PDF" not in resp.content[:1024]:
            return "SCRAPE_ERROR: pdf_extract — URL returned HTML, not a PDF"
        pdf_bytes = resp.content
    except Exception as e:
        return f"SCRAPE_ERROR: pdf_extract — download failed: {e}"

    log.info("pdf_extract downloaded %d KB from %s", len(pdf_bytes) // 1024, url)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        # Attempt 1: pdfplumber — tables + text
        pdfplumber_result = ""
        page_count = 0
        try:
            sections: list[str] = []
            total_chars = 0

            with pdfplumber.open(tmp_path) as pdf:
                page_count = len(pdf.pages)
                sections.append(
                    f"[Source: {url}]\n[PDF — {page_count} pages; "
                    f"extracting first {min(page_count, MAX_PAGES)}]\n"
                )
                for page_num, page in enumerate(pdf.pages[:MAX_PAGES], start=1):
                    parts: list[str] = [f"\n--- Page {page_num} ---"]

                    for table in (page.extract_tables() or []):
                        if not table:
                            continue
                        rows = [
                            "| " + " | ".join(
                                str(c).strip().replace("\n", " ") if c else "" for c in row
                            ) + " |"
                            for row in table if any(row)
                        ]
                        if rows:
                            parts.append("\n".join(rows))

                    plain = (page.extract_text(x_tolerance=3, y_tolerance=3) or "").strip()
                    if plain:
                        kept = [ln for ln in plain.splitlines()
                                if ln.strip() and not all(c in "0123456789,. -|()" for c in ln.strip())]
                        if kept:
                            parts.append("\n".join(kept))

                    page_text = "\n".join(parts)
                    if total_chars + len(page_text) > CHAR_LIMIT:
                        remaining = CHAR_LIMIT - total_chars
                        if remaining > 100:
                            sections.append(page_text[:remaining])
                        sections.append(f"\n[... truncated at {CHAR_LIMIT:,} chars ...]")
                        break
                    sections.append(page_text)
                    total_chars += len(page_text)

            pdfplumber_result = "\n".join(sections).strip()
        except Exception as e:
            log.warning("pdfplumber failed for %s: %s", url, e)

        if pdfplumber_result and len(pdfplumber_result) >= 50:
            log.info("pdf_extract (pdfplumber) — %d chars from %s", len(pdfplumber_result), url)
            return pdfplumber_result

        # Attempt 2: pymupdf4llm
        try:
            import pymupdf4llm
            pages = list(range(min(page_count, MAX_PAGES))) if page_count else None
            md = pymupdf4llm.to_markdown(tmp_path, **({"pages": pages} if pages else {})).strip()
            if md and len(md) >= 50:
                if len(md) > CHAR_LIMIT:
                    md = md[:CHAR_LIMIT] + f"\n[... truncated at {CHAR_LIMIT:,} chars ...]"
                log.info("pdf_extract (pymupdf4llm) — %d chars from %s", len(md), url)
                return f"[Source: {url}]\n[Extracted via pymupdf4llm]\n\n{md}"
        except ImportError:
            pass
        except Exception as e:
            log.warning("pymupdf4llm failed for %s: %s", url, e)

        return (
            "SCRAPE_EMPTY: pdf_extract — no extractable text "
            "(tried pdfplumber and pymupdf4llm; may be a scanned image without OCR)"
        )

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
