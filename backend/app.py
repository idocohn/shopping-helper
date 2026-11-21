from __future__ import annotations
import json
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from openpyxl.utils.exceptions import InvalidFileException
from xlrd import XLRDError

from matching.match_basket import load_catalog, read_basket, match_basket

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CATALOG = DATA / "products.json"
MAX_BASKET_BYTES = 5 * 1024 * 1024
MAX_BASKET_ROWS = 1000

app = FastAPI(title="Hahishook Switcher")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_cache: dict = {"mtime": 0.0, "rows": []}


def _catalog_rows() -> list[dict]:
    """Read the JSON catalog from disk, caching by mtime so repeated requests are cheap."""
    if not CATALOG.exists():
        return []
    mtime = CATALOG.stat().st_mtime
    if mtime != _cache["mtime"]:
        _cache["rows"] = json.loads(CATALOG.read_text(encoding="utf-8"))
        _cache["mtime"] = mtime
    return _cache["rows"]


@app.get("/api/health")
def health():
    rows = _catalog_rows()
    return {"ok": True, "products": len(rows), "catalog_exists": CATALOG.exists()}


@app.get("/api/categories")
def categories():
    rows = _catalog_rows()
    counts: dict[str, int] = {}
    for r in rows:
        c = r.get("category") or ""
        if c:
            counts[c] = counts.get(c, 0) + 1
    return [{"category": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]


@app.get("/api/sources")
def sources():
    rows = _catalog_rows()
    counts: dict[str, int] = {}
    for r in rows:
        s = r.get("source") or ""
        if s:
            counts[s] = counts.get(s, 0) + 1
    return [{"source": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]


@app.get("/api/products")
def products(
    q: str = "",
    category: str = "",
    source: str = "",
    in_stock: bool | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    limit: int = 50,
    offset: int = 0,
):
    rows = _catalog_rows()
    if not rows:
        return {"total": 0, "items": []}
    ql = q.strip().lower()
    cl = category.strip().lower()
    sl = source.strip().lower()

    def keep(r: dict) -> bool:
        if ql:
            hay = " ".join(str(r.get(f) or "") for f in ("name", "category", "size_text", "brand", "source")).lower()
            if ql not in hay:
                return False
        if cl and cl not in (r.get("category") or "").lower():
            return False
        if sl and (r.get("source") or "").lower() != sl:
            return False
        if in_stock is not None and bool(r.get("in_stock")) != in_stock:
            return False
        price = r.get("price_nis")
        if min_price is not None and (price is None or price < min_price):
            return False
        if max_price is not None and (price is None or price > max_price):
            return False
        return True

    filtered = [r for r in rows if keep(r)]
    return {"total": len(filtered), "items": filtered[offset : offset + limit]}


@app.post("/api/match")
def match(file: UploadFile = File(...), min_score: int = Query(70, ge=0, le=100)):
    if not CATALOG.exists():
        raise HTTPException(status_code=503, detail="Catalog not built yet. Run the scraper first.")
    filename = file.filename or ""
    if Path(filename).suffix.lower() not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(status_code=400, detail="Upload a CSV, XLSX, or XLS file.")
    if file.size is not None and file.size > MAX_BASKET_BYTES:
        raise HTTPException(status_code=413, detail="The basket file must be 5 MB or smaller.")
    try:
        basket = read_basket(file.file, filename=filename, nrows=MAX_BASKET_ROWS + 1)
    except (ValueError, BadZipFile, InvalidFileException, XLRDError, ParseError, OSError, KeyError) as error:
        raise HTTPException(status_code=400, detail="Could not read the basket. Include a header and at least one product row.") from error
    if len(basket) > MAX_BASKET_ROWS:
        raise HTTPException(status_code=413, detail=f"The basket can contain up to {MAX_BASKET_ROWS:,} rows.")
    catalog = load_catalog(CATALOG)
    result = match_basket(basket, catalog, min_score)
    return result.fillna("").to_dict(orient="records")

