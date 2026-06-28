from __future__ import annotations
import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from rich.console import Console
from .utils import BASE_URL, HEADERS, normalize_url, looks_like_category

console = Console()

async def fetch(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=30)
    r.raise_for_status()
    return r.text

async def discover_categories(start_url: str = BASE_URL, limit: int = 500) -> list[str]:
    """Crawl the homepage and every category page found to collect every
    /product-category/ URL Hahishook exposes. Bounded by `limit` pages fetched."""
    seen_pages: set[str] = set()
    categories: set[str] = set()
    queue = [start_url]
    async with httpx.AsyncClient() as client:
        while queue and len(seen_pages) < limit:
            url = queue.pop(0)
            if url in seen_pages:
                continue
            seen_pages.add(url)
            try:
                html = await fetch(client, url)
            except Exception as e:
                console.print(f"[yellow]skip {url}: {e}[/yellow]")
                continue
            soup = BeautifulSoup(html, "lxml")
            for a in soup.select("a[href]"):
                href = normalize_url(a.get("href", ""))
                if not href.startswith(BASE_URL):
                    continue
                parsed = urlparse(href)
                clean = parsed._replace(query="", fragment="").geturl().rstrip("/")
                if looks_like_category(clean):
                    if clean not in categories:
                        categories.add(clean)
                        # Follow category pages so nested categories are discovered too.
                        queue.append(clean)
                elif parsed.netloc.endswith("hahishook.com") and parsed.path in {"/", ""}:
                    queue.append(clean)
    console.print(f"Discovered {len(categories)} categories across {len(seen_pages)} pages")
    return sorted(categories)

async def main() -> None:
    out = Path("data/categories.json")
    out.parent.mkdir(exist_ok=True)
    categories = await discover_categories()
    out.write_text(json.dumps(categories, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"Wrote {len(categories)} categories to {out}")

if __name__ == "__main__":
    asyncio.run(main())
