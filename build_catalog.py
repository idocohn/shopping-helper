"""Catalog orchestrator.

Runs every configured source (Hahishook scraper, Shufersal transparency
feed, ...), tags each product with its source, dedupes within each source,
and writes the combined catalog to ``data/products.{json,csv,sqlite}``.

Adding a new source:

    1. Create ``sources/<name>.py`` exposing ``scrape(...) -> list[Product]``
       that returns products with ``source="<name>"`` set on every record.
    2. Add an entry to the ``SOURCES`` list below.

Sources are independent: if one fails, the others still run and the partial
catalog is still written. Per-source counts and failures are logged at the
end.
"""
from __future__ import annotations

import argparse
import asyncio
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
        print(f"  {name}: {len(result)} products")
        return name, result, None
    except Exception as e:
        print(f"  {name}: FAILED with {type(e).__name__}: {e}")
        traceback.print_exc()
        return name, [], e


async def build(outdir: Path, only: list[str] | None = None) -> None:
    todo = SOURCES if not only else [s for s in SOURCES if s[0] in only]
    if not todo:
        raise SystemExit(f"No matching sources. Available: {[s[0] for s in SOURCES]}")
    results = []
    for name, fn, is_async in todo:
        results.append(await run_source(name, fn, is_async))
    all_products: list[Product] = []
    for _name, prods, _err in results:
        all_products.extend(prods)
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
        if len(failures) == len(results):
            raise SystemExit(1)  # everything failed -> fail the workflow


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the merged shopping catalog.")
    ap.add_argument("--outdir", default="data")
    ap.add_argument(
        "--only",
        nargs="+",
        help=f"Run only these sources. Available: {[s[0] for s in SOURCES]}",
    )
    args = ap.parse_args()
    asyncio.run(build(Path(args.outdir), only=args.only))


if __name__ == "__main__":
    main()
