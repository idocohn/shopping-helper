"""Catalog orchestrator.

Runs every configured source (Hahishook scraper, Shufersal transparency
feed, ...), tags each product with its source, dedupes within each source,
and writes the combined catalog to ``data/products.{json,csv,sqlite}``.

Adding a new source:

    1. Create ``sources/<name>.py`` exposing ``scrape(...) -> list[Product]``
       that returns products with ``source="<name>"`` set on every record.
    2. Add an entry to the ``SOURCES`` list below.

Sources are independent: if one fails, the others still run and the partial
catalog can still be written. Use --preserve-existing to keep the last
successful data for sources skipped or unavailable during a refresh.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import traceback
from pathlib import Path

from scraper.models import Product
from scraper.scrape import dedupe, scrape_hahishook, write_outputs
from sources import shufersal


async def _hahishook() -> list[Product]:
    return await scrape_hahishook()


def _shufersal() -> list[Product]:
    return shufersal.scrape(store_id="003")


SOURCES = [
    ("hahishook", _hahishook, True),    # async
    ("shufersal", _shufersal, False),   # sync
]


async def run_source(name: str, fn, is_async: bool) -> tuple[str, list[Product], Exception | None]:
    print(f"\n=== Source: {name} ===")
    try:
        result = await fn() if is_async else fn()
    except Exception as e:
        print(f"  {name}: FAILED with {type(e).__name__}: {e}")
        traceback.print_exc()
        return name, [], e
    if not result:
        print(f"  {name}: FAILED (no products returned)")
        return name, [], ValueError("Source returned no products")
    print(f"  {name}: {len(result)} products")
    return name, result, None


async def build(outdir: Path, only: list[str] | None = None, preserve_existing: bool = False) -> None:
    todo = SOURCES if not only else [s for s in SOURCES if s[0] in only]
    if not todo:
        raise SystemExit(f"No matching sources. Available: {[s[0] for s in SOURCES]}")
    results = []
    for name, fn, is_async in todo:
        results.append(await run_source(name, fn, is_async))
    refreshed = {name for name, _products, error in results if error is None}
    if not refreshed:
        raise SystemExit("No source returned products. The catalog was left alone.")

    all_products = [product for _name, products, _error in results for product in products]
    previous_catalog = outdir / "products.json"
    if preserve_existing and previous_catalog.exists():
        previous_rows = json.loads(previous_catalog.read_text(encoding="utf-8"))
        retained = [
            Product.model_validate({
                **row,
                "source": row.get("source") or "hahishook",
                "scraped_at": row.get("scraped_at") or "",
            })
            for row in previous_rows
            if (row.get("source") or "hahishook") not in refreshed
        ]
        if retained:
            print(f"Retaining {len(retained)} existing records from: {', '.join(sorted({p.source for p in retained}))}")
            all_products.extend(retained)
        source_order = {name: index for index, (name, _, _) in enumerate(SOURCES)}
        all_products.sort(key=lambda product: source_order.get(product.source, len(source_order)))
    all_products = dedupe(all_products)
    write_outputs(all_products, outdir)
    print(f"\n=== Combined catalog ===")
    by_source: dict[str, int] = {}
    for p in all_products:
        by_source[p.source] = by_source.get(p.source, 0) + 1
    for src, n in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"  {src}: {n}")
    print(f"  TOTAL: {len(all_products)} products written to {outdir}")
    failures = [name for name, _p, err in results if err is not None]
    if failures:
        print(f"\nWARNING: {len(failures)} source(s) failed: {failures}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the merged shopping catalog.")
    ap.add_argument("--outdir", default="data")
    ap.add_argument("--preserve-existing", action="store_true", help="Keep existing rows for sources that fail or aren't selected.")
    ap.add_argument(
        "--only",
        nargs="+",
        help=f"Run only these sources. Available: {[s[0] for s in SOURCES]}",
    )
    args = ap.parse_args()
    asyncio.run(build(Path(args.outdir), only=args.only, preserve_existing=args.preserve_existing))


if __name__ == "__main__":
    main()
