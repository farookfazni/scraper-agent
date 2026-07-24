"""
save_result — the agent calls this once when it has finished extracting data.
Always writes the same JSON envelope to disk and returns the file path.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from agents import function_tool

log = logging.getLogger(__name__)


@function_tool
def save_result(result_json: str, schema_name: str, output_dir: str = "output") -> str:
    """
    Save the scraped result to a structured JSON file.
    Call this ONCE at the end, after all scraping and extraction is complete.

    The JSON you pass must follow this envelope exactly:
    {
      "status": "success" | "partial" | "failed",
      "data": { ... extracted fields ... },
      "sources": ["url1", "url2"],
      "tools_used": ["crawl4ai", "pdf_extract"],
      "errors": [],
      "raw_text": null
    }

    Args:
        result_json:  JSON string matching the envelope above.
        schema_name:  Short label for the output filename (e.g. "cse_financials").
        output_dir:   Directory to write the file (created if it doesn't exist).

    Returns:
        "Saved: <path>" on success, or an error message.
    """
    try:
        result = json.loads(result_json)
    except json.JSONDecodeError as e:
        return f"ERROR: invalid result_json — {e}"

    # Always inject _meta
    result["_meta"] = {
        "schema_name": schema_name,
        "saved_at":    datetime.now().isoformat(timespec="seconds"),
        "version":     "1.0",
    }

    try:
        abs_dir = os.path.abspath(output_dir)
        os.makedirs(abs_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in schema_name)
        filename = f"{safe_name}_{ts}.json"
        path = os.path.join(abs_dir, filename)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        log.info("Result saved → %s", filename)
        return f"Saved: {path}"
    except Exception as e:
        log.error("Failed to save result: %s", e)
        return f"ERROR: could not save result — {e}"
