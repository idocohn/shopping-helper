from __future__ import annotations
import argparse
import asyncio
import csv
import json
import re
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from rich.progress import Progress
from .discover import discover_categories
from .models import Product
from .utils import HEADERS, category_url, clean_text, normalize_url, price_to_float

async def fetch(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=45)
    r.raise_for_status()
    return r.text

def get_category_name(soup: BeautifulSoup) -> str | None:
    h1 = soup.find("h1")
    if h1:
        return clean_text(h1.get_text(" ")).replace("קטגוריה:", "").strip()
    title = soup.find("title")
    return clean_text(title.get_text(" ")) if title else None

def pagination_urls(soup: BeautifulSoup, url: str) -> list[str]:
    """Return every /page/N/ URL for this category.

    WooCommerce only renders [1, 2, 3, …, last] on page 1, so we read the
    largest N from the pagination nav and generate the full range ourselves.
    """
    base = url.rstrip("/")
    max_page = 1
    for a in soup.select(".woocommerce-pagination a[href]"):
        href = normalize_url(a["href"], url)
        if category_url(href) != category_url(url):
            continue
        m = re.search(r"/page/(\d+)/?$", urlparse(href).path)
        if m:
            n = int(m.group(1))
            if n > max_page:
                max_page = n
    return [url] + [f"{base}/page/{n}/" for n in range(2, max_page + 1)]

def parse_product_cards(html: str, page_url: str, category: str | None) -> list[Product]:
    soup = BeautifulSoup(html, "lxml")
    candidates = soup.select("li.product, .product.type-product, .product-small")
    cards = []
    for card in candidates:
        raw = clean_text(card.get_text(" ")) or ""
        if len(raw) < 8:
            continue
        name_el = card.select_one("h2, h3, .woocommerce-loop-product__title, .product-title, .name, a[aria-label]")
        name = clean_text(name_el.get_text(" ")) if name_el else None
        if not name:
            aria = card.select_one("a[aria-label]")
            name = clean_text(aria.get("aria-label")) if aria else None
        if name:
            name = re.sub(r"^(הוספה‎? לסל|הוספת\s+\S+|כמות של)\s*", "", name).strip()
        # Better fallback: use image alt.
        if not name:
            img = card.select_one("img[alt]")
            name = clean_text(img.get("alt")) if img else None
        if not name or name in {"Image", "תמונה"}:
            continue
        price_el = (
            card.select_one(".price ins .woocommerce-Price-amount")
            or card.select_one(".price .woocommerce-Price-amount")
            or card.select_one(".price")
        )
        price_text = clean_text(price_el.get_text(" ")) if price_el else None
        price_nis = price_to_float(price_text)
        link = None
        a = card.select_one("a.woocommerce-LoopProduct-link[href], a[href*='/product/']")
        if a:
            link = normalize_url(a["href"], page_url)
        img = card.select_one("img[src], img[data-src]")
        src = (img.get("data-src") or img.get("src")) if img else None
        img_url = normalize_url(src, page_url) if src else None
        # Size is often after title in h5/short description or Hebrew gram/kilo/ml tokens.
        subtitle = card.select_one(".product-subtitle")
        size_text = clean_text(subtitle.get_text(" ")) if subtitle else None
        m = re.search(r"((?:\d+(?:[.,]\d+)?)\s*(?:גרם|ג׳|קילו|ק״ג|קג|מ״ל|מל|ליטר|יח׳|יחידות)[^₪]{0,40})", raw)
        if not size_text and m:
            size_text = clean_text(m.group(1))
        unit_price = card.select_one(".price-per-unit")
        unit_price_text = clean_text(unit_price.get_text(" ")) if unit_price else None
        m2 = re.search(r"(\d+(?:\.\d+)?\s*₪\s*/\s*(?:100\s*ג|יח|קילו|ליטר)|\d+(?:\.\d+)?\s*אג'\s*/\s*יח)", raw)
        if not unit_price_text and m2:
            unit_price_text = clean_text(m2.group(1))
        bulk_price_text = None
        m3 = re.search(r"(₪?\d+(?:\.\d+)?\s*ל-\d+\s*יחידות[^+–-]{0,20})", raw)
        if m3:
            bulk_price_text = clean_text(m3.group(1))
        saving_text = None
        m4 = re.search(r"(\d+(?:\.\d+)?\s*₪\s*חסכון)", raw)
        if m4:
            saving_text = clean_text(m4.group(1))
        pid = None
        pid_el = card.select_one("[data-product_id]")
        if pid_el:
            pid = pid_el.get("data-product_id")
        if not pid:
            pid = next((cls.removeprefix("post-") for cls in card.get("class", []) if re.fullmatch(r"post-\d+", cls)), None)
        cards.append(Product(
            product_id=pid,
            name=name,
            category=category,
            size_text=size_text,
            price_nis=price_nis,
            unit_price_text=unit_price_text,
            bulk_price_text=bulk_price_text,
            saving_text=saving_text,
            product_url=link,
            image_url=img_url,
            in_stock=("outofstock" not in card.get("class", []) and "אזל" not in raw and "Out of stock" not in raw),
            raw_text=raw[:1500],
        ))
    return dedupe(cards)

async def scrape_category(client: httpx.AsyncClient, url: str) -> list[Product]:
    try:
        html = await fetch(client, url)
    except httpx.HTTPStatusError as error:
        if error.response.status_code not in {404, 410}:
            raise
        print(f"Category removed ({error.response.status_code}): {url}")
        return []
    soup = BeautifulSoup(html, "lxml")
    category = get_category_name(soup)
    pages = pagination_urls(soup, url)
    products: list[Product] = []
    for purl in pages:
        page_html = html if purl == url else await fetch(client, purl)
        products.extend(parse_product_cards(page_html, purl, category))
        await asyncio.sleep(0.35)
    return products

def dedupe(products: list[Product]) -> list[Product]:
    """Deduplicate within a source — different sources can ship the same item
    at different prices, so source is always part of the key."""
    out = {}
    for p in products:
        key = (p.source, p.product_id) if p.product_id else (
            p.source, p.name, p.size_text, p.price_nis, p.product_url,
        )
        if key not in out:
            out[key] = p
    return list(out.values())

def write_outputs(products: list[Product], outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=outdir) as directory:
        staging = Path(directory)
        _write_outputs(products, staging)
        for name in ("products.csv", "catalog.sqlite", "products.json"):
            (staging / name).replace(outdir / name)


def _write_outputs(products: list[Product], outdir: Path) -> None:
    rows = [p.model_dump() for p in products]
    (outdir / "products.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with (outdir / "products.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else Product(name="x").model_dump().keys())
        writer.writeheader(); writer.writerows(rows)
    con = sqlite3.connect(outdir / "catalog.sqlite")
    con.execute("drop table if exists products")
    con.execute("""create table products (
        source text, product_id text, name text, brand text, category text, size_text text,
        price_nis real, unit_price_text text, bulk_price_text text, saving_text text,
        badges text, product_url text, image_url text, in_stock integer, raw_text text, scraped_at text
    )""")
    con.executemany("insert into products values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        (r["source"], r["product_id"], r["name"], r["brand"], r["category"], r["size_text"], r["price_nis"], r["unit_price_text"], r["bulk_price_text"], r["saving_text"], json.dumps(r["badges"], ensure_ascii=False), r["product_url"], r["image_url"], 1 if r["in_stock"] else 0, r["raw_text"], r["scraped_at"])
        for r in rows
    ])
    con.commit(); con.close()

async def scrape_hahishook(
    categories_path: Path | None = Path("data/categories.json"),
    discover_first: bool = False,
    limit: int = 0,
) -> list[Product]:
    """High-level entry point: optionally discover categories, scrape them all,
    dedupe, return the product list. Does not write any files."""
    if categories_path and not discover_first and categories_path.exists():
        categories = json.loads(categories_path.read_text(encoding="utf-8"))
    else:
        categories = []
    if not categories:
        # Empty/missing file or forced rediscovery -> walk the site.
        print("Discovering Hahishook categories...")
        categories = await discover_categories()
        if categories_path:
            categories_path.parent.mkdir(parents=True, exist_ok=True)
            categories_path.write_text(
                json.dumps(categories, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    categories = list(dict.fromkeys(clean for url in categories if (clean := category_url(url))))
    if limit:
        categories = categories[:limit]
    print(f"Scraping {len(categories)} Hahishook categories")
    all_products: list[Product] = []
    async with httpx.AsyncClient() as client:
        with Progress() as progress:
            task = progress.add_task("Hahishook", total=len(categories))
            for url in categories:
                all_products.extend(await scrape_category(client, url))
                progress.advance(task)
    return dedupe(all_products)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--categories", default="data/categories.json", help="JSON list of category URLs. Auto-discovered if missing.")
    parser.add_argument("--outdir", default="data")
    parser.add_argument("--limit", type=int, default=0, help="Limit categories for testing")
    parser.add_argument("--discover", action="store_true", help="Force re-discovery even if categories file exists")
    args = parser.parse_args()
    products = await scrape_hahishook(
        categories_path=Path(args.categories),
        discover_first=args.discover,
        limit=args.limit,
    )
    write_outputs(products, Path(args.outdir))
    print(f"Wrote {len(products)} products to {args.outdir}")

if __name__ == "__main__":
    asyncio.run(main())
