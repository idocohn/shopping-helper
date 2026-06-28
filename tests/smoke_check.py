"""Stdlib-only smoke test: fetch a Hahishook category page and verify the
selectors used by `scraper/scrape.py` find product cards in the live HTML.

Does NOT modify the local environment. Run with the system Python:
    python tests\\smoke_check.py
"""
from __future__ import annotations
import re
import sys
import urllib.request
from html.parser import HTMLParser

URL = "https://hahishook.com/product-category/%D7%9E%D7%95%D7%9E%D7%9C%D7%A6%D7%99%D7%9D/"
HEADERS = {"User-Agent": "Mozilla/5.0 compatible; HahishookSmokeCheck/0.1"}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    # WP/StoreFront serves utf-8 with charset header.
    return data.decode("utf-8", errors="replace")


class TagCounter(HTMLParser):
    """Count occurrences of tag/class combinations we care about."""

    INTERESTING = {
        ("li", "product"),
        ("div", "product"),
        ("a", "add_to_cart_button"),
        ("a", "ajax_add_to_cart"),
        ("a", "woocommerce-LoopProduct-link"),
        ("h2", "woocommerce-loop-product__title"),
        ("span", "woocommerce-Price-amount"),
        ("ul", "products"),
        ("nav", "woocommerce-pagination"),
    }

    def __init__(self) -> None:
        super().__init__()
        self.counts: dict[tuple[str, str], int] = {}

    def handle_starttag(self, tag: str, attrs):
        classes = ""
        for k, v in attrs:
            if k == "class" and v:
                classes = v
                break
        if not classes:
            return
        class_set = set(classes.split())
        for t, cls in self.INTERESTING:
            if tag == t and cls in class_set:
                self.counts[(t, cls)] = self.counts.get((t, cls), 0) + 1


def main() -> int:
    print(f"Fetching: {URL}")
    try:
        html = fetch(URL)
    except Exception as e:
        print(f"FAILED to fetch: {e}", file=sys.stderr)
        return 2

    print(f"OK: {len(html):,} bytes")

    counter = TagCounter()
    counter.feed(html)
    print("\nSelector hit counts (tag.class):")
    if not counter.counts:
        print("  (none found - the site markup may have changed)")
    for (tag, cls), n in sorted(counter.counts.items(), key=lambda x: -x[1]):
        print(f"  {tag}.{cls:40s} {n}")

    # Quick pagination signals.
    page_links = len(re.findall(r"/page/\d+/", html))
    paged_q = len(re.findall(r"[?&]paged=\d+", html))
    results_msg = re.search(
        r"\u05de\u05e6\u05d9\u05d2[^<]{0,40}\u05de\u05ea\u05d5\u05da\s*(\d+)\s*\u05ea\u05d5\u05e6\u05d0\u05d5\u05ea",
        html,
    )
    print("\nPagination signals:")
    print(f"  /page/N/ links: {page_links}")
    print(f"  ?paged=N links: {paged_q}")
    if results_msg:
        print(f"  total results reported on page: {results_msg.group(1)}")

    # Price marker tally.
    prices = re.findall(r"\u20aa\s?\d", html)
    print(f"\n\u20aa-prefixed price hits in HTML: {len(prices)}")

    found_cards = (
        counter.counts.get(("li", "product"), 0)
        + counter.counts.get(("div", "product"), 0)
    )
    if found_cards == 0:
        print("\nRESULT: no product cards found - scraper will likely return 0 items.")
        return 1
    print(f"\nRESULT: found {found_cards} product card elements - scraper selectors look compatible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
