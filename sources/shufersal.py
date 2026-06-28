"""Shufersal source: pulls product + price data from the official Israeli
price-transparency portal (https://prices.shufersal.co.il/).

The portal exposes daily-refreshed XML files per store. We want the
``PriceFull`` files (full catalog snapshots); the smaller ``Price`` files
are deltas and useless on their own. File URLs are signed Azure Blob SAS
URLs that expire within minutes, so we always fetch fresh.

The portal exposes a filtered endpoint:

    https://prices.shufersal.co.il/FileObject/UpdateCategory
        ?catID=2          # 2 = PriceFull (1=Price, 3=Promo, 4=PromoFull, 5=Stores)
        &storeId={N}      # 0 = all stores; positive int = one store

The XML schema is mandated by Israeli law ("\u05d7\u05d5\u05e7 \u05de\u05d7\u05d9\u05e8\u05d5\u05ea \u05e9\u05d5\u05d5\u05d9\u05dd"), so
the same parser works for the other major chains (Rami Levy, Victory,
Yochananof, Tiv Taam, ...) - each just has a different portal hostname.
"""
from __future__ import annotations

import gzip
import re
from datetime import datetime
from typing import Iterable

import httpx
from bs4 import BeautifulSoup
from lxml import etree

from scraper.models import Product
from scraper.utils import HEADERS

PORTAL_URL = "https://prices.shufersal.co.il/"
PRICE_FULL_CAT_ID = 2
FILENAME_RE = re.compile(
    r"(PriceFull|Price)(\d{13})-(\d{3})-(\d{3})-(\d{8})-(\d{6})"
)


def _fetch(client: httpx.Client, url: str) -> str:
    r = client.get(url, headers=HEADERS, follow_redirects=True, timeout=30)
    r.raise_for_status()
    return r.text


def _parse_listing(html: str) -> list[dict]:
    """Extract (kind, store_id, timestamp, url) from a portal listing HTML."""
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for a in soup.select("td a[href*='blob.core.windows.net']"):
        href = a["href"]
        m = FILENAME_RE.search(href)
        if not m:
            continue
        kind, chain_id, sub_chain, store_id, ymd, hms = m.groups()
        rows.append(
            {
                "kind": kind,
                "chain_id": chain_id,
                "sub_chain_id": sub_chain,
                "store_id": store_id,
                "timestamp": ymd + hms,
                "url": href,
            }
        )
    return rows


def latest_price_full_url(client: httpx.Client, store_id: str) -> dict | None:
    """Return the freshest PriceFull file entry for the given store."""
    store_int = int(store_id)
    url = (
        f"{PORTAL_URL}FileObject/UpdateCategory"
        f"?catID={PRICE_FULL_CAT_ID}&storeId={store_int}"
    )
    rows = _parse_listing(_fetch(client, url))
    full = [r for r in rows if r["kind"] == "PriceFull" and r["store_id"] == store_id]
    if not full:
        return None
    return max(full, key=lambda r: r["timestamp"])


def _download_xml(client: httpx.Client, url: str) -> bytes:
    r = client.get(url, headers=HEADERS, follow_redirects=True, timeout=60)
    r.raise_for_status()
    return gzip.decompress(r.content)


def _text(el, tag: str) -> str | None:
    if el is None:
        return None
    for child in el:
        if isinstance(child.tag, str) and child.tag.lower() == tag.lower():
            return (child.text or "").strip() or None
    return None


def _parse_xml(xml_bytes: bytes, store_id: str) -> Iterable[Product]:
    root = etree.fromstring(xml_bytes)
    items_parent = None
    for el in root.iter():
        if isinstance(el.tag, str) and el.tag.lower() == "items":
            items_parent = el
            break
    if items_parent is None:
        return
    for item in items_parent:
        if not isinstance(item.tag, str) or item.tag.lower() != "item":
            continue
        code = _text(item, "ItemCode")
        name = _text(item, "ItemName") or _text(item, "ManufacturerItemDescription")
        if not name:
            continue
        try:
            price = float(_text(item, "ItemPrice"))
        except (TypeError, ValueError):
            price = None
        try:
            unit_price = float(_text(item, "UnitOfMeasurePrice"))
        except (TypeError, ValueError):
            unit_price = None
        qty = _text(item, "Quantity")
        unit = _text(item, "UnitOfMeasure") or _text(item, "UnitQty")
        size_text = " ".join(x for x in (qty, unit) if x) or None
        unit_price_text = (
            f"\u20aa{unit_price:.2f}/{unit}" if unit_price is not None and unit else None
        )
        brand = _text(item, "ManufacturerName")
        in_stock = _text(item, "ItemStatus") in (None, "1")
        yield Product(
            source="shufersal",
            product_id=code,
            name=name,
            brand=brand,
            category=f"shufersal store {store_id}",
            size_text=size_text,
            price_nis=price,
            unit_price_text=unit_price_text,
            product_url=None,
            image_url=None,
            in_stock=in_stock,
            raw_text=f"shufersal store {store_id}, item {code}",
        )


def scrape(store_id: str = "003") -> list[Product]:
    """Download the latest Shufersal PriceFull XML for ``store_id`` and
    return parsed Product records.

    Defaults to store 003 (Shelly Givatayim - Sirkin). Pass any other store
    id (e.g. ``"001"`` for Shelly Tel Aviv - Ben Yehuda) to compare across
    branches. ``storeId=0`` would mean "all stores" on the portal but here we
    expect a real numeric store id.
    """
    print(f"Looking for latest PriceFull for Shufersal store {store_id}...")
    with httpx.Client() as client:
        entry = latest_price_full_url(client, store_id)
        if entry is None:
            print(f"  No PriceFull file found for store {store_id}.")
            return []
        pretty_ts = datetime.strptime(entry["timestamp"], "%Y%m%d%H%M%S").isoformat()
        print(f"  Downloading PriceFull ({pretty_ts})...")
        xml = _download_xml(client, entry["url"])
    products = list(_parse_xml(xml, store_id))
    print(f"  Parsed {len(products)} items from Shufersal store {store_id}")
    return products


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    sid = sys.argv[1] if len(sys.argv) > 1 else "003"
    items = scrape(sid)
    out = Path("data/shufersal-preview.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(
        json.dumps([p.model_dump() for p in items[:50]], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote preview of first 50 items to {out}")
