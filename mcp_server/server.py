"""Hahishook MCP server.

Exposes the unofficial Hahishook catalog (scraped by this repo and published
as static JSON on GitHub Pages) as tools for any MCP-aware AI client
(Claude Desktop, Cursor, Continue, ...).

Configuration is via environment variables:

  HAHISHOOK_CATALOG_URL   URL of products.json. Defaults to the GH Pages
                          publication of this repo. Point at a local file
                          path (file://...) to develop offline.
  HAHISHOOK_CATALOG_TTL   Seconds to cache the catalog in memory. Default 3600.

Run directly for stdio transport:

  python -m mcp_server.server
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any

from mcp.server.fastmcp import FastMCP

DEFAULT_URL = os.environ.get(
    "HAHISHOOK_CATALOG_URL",
    "https://idocohn.github.io/shopping-helper/products.json",
)
TTL_SECONDS = int(os.environ.get("HAHISHOOK_CATALOG_TTL", "3600"))

_cache: dict[str, Any] = {"rows": [], "fetched_at": 0.0}

mcp = FastMCP("hahishook")


def _load() -> list[dict]:
    now = time.time()
    if _cache["rows"] and now - _cache["fetched_at"] < TTL_SECONDS:
        return _cache["rows"]
    req = urllib.request.Request(
        DEFAULT_URL, headers={"User-Agent": "hahishook-mcp/0.1"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - trusted URL from env
        rows = json.loads(r.read().decode("utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError(
            f"Catalog at {DEFAULT_URL} did not return a JSON list"
        )
    _cache["rows"] = rows
    _cache["fetched_at"] = now
    return rows


def _text_match(row: dict, query: str) -> bool:
    if not query:
        return True
    hay = " ".join(
        str(row.get(f) or "")
        for f in ("name", "category", "size_text", "brand")
    ).lower()
    return query.lower() in hay


@mcp.tool()
def search_products(
    query: str = "",
    category: str | None = None,
    in_stock: bool | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    limit: int = 20,
) -> dict:
    """Search the Hahishook catalog.

    Args:
        query: Free-text match against name, category, size, brand. Hebrew works.
        category: Substring filter on category name.
        in_stock: If true, only show products marked in stock.
        min_price: Minimum price in NIS.
        max_price: Maximum price in NIS.
        limit: Max items returned. Capped at 100.

    Returns:
        {"total": int, "items": [product, ...]}
    """
    rows = _load()
    out = []
    for r in rows:
        if not _text_match(r, query):
            continue
        if category and category.lower() not in (r.get("category") or "").lower():
            continue
        if in_stock is not None and bool(r.get("in_stock")) != in_stock:
            continue
        price = r.get("price_nis")
        if min_price is not None and (price is None or price < min_price):
            continue
        if max_price is not None and (price is None or price > max_price):
            continue
        out.append(r)
    limit = max(1, min(limit, 100))
    return {"total": len(out), "items": out[:limit]}


@mcp.tool()
def list_categories() -> list[dict]:
    """List every category in the catalog with product counts, sorted descending."""
    rows = _load()
    counts: dict[str, int] = {}
    for r in rows:
        c = r.get("category") or ""
        if c:
            counts[c] = counts.get(c, 0) + 1
    return [
        {"category": k, "count": v}
        for k, v in sorted(counts.items(), key=lambda x: -x[1])
    ]


@mcp.tool()
def get_product(product_url: str) -> dict | None:
    """Return a single product by its full hahishook.com product URL, or null."""
    for r in _load():
        if r.get("product_url") == product_url:
            return r
    return None


@mcp.tool()
def catalog_info() -> dict:
    """Return metadata about the loaded catalog (source URL, size, age)."""
    rows = _load()
    return {
        "source_url": DEFAULT_URL,
        "product_count": len(rows),
        "fetched_at": _cache["fetched_at"],
        "ttl_seconds": TTL_SECONDS,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
