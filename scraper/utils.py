from __future__ import annotations
import re
from urllib.parse import urljoin, urlparse

BASE_URL = "https://hahishook.com"
CATEGORY_PREFIX = "/product-category/"

# Browser-like headers. Hahishook (Cloudflare in front of it) returns 403 to
# unknown UAs from cloud IPs, so we present as a recent desktop Chrome.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "he,en-US;q=0.9,en;q=0.8",
    "Referer": BASE_URL + "/",
}

def clean_text(s: str | None) -> str | None:
    if s is None:
        return None
    return re.sub(r"\s+", " ", s).strip()

def normalize_url(url: str, base: str = BASE_URL) -> str:
    return urljoin(base, url.split("#")[0])

def is_hahishook_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host in {"hahishook.com", "www.hahishook.com"}

def price_to_float(text: str | None) -> float | None:
    if not text:
        return None
    # Handles ₪13.00, 13.00₪, 29.2‏₪, Hebrew bidi chars.
    cleaned = text.replace(",", "").replace("₪", " ")
    m = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    return float(m.group(1)) if m else None

def looks_like_category(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.endswith("hahishook.com") and parsed.path.startswith(CATEGORY_PREFIX)
