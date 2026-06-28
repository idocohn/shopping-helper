from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import pandas as pd
from rapidfuzz import fuzz, process

HEBREW_NOISE = ["יחידות", "יח׳", "גרם", "ג׳", "קילו", "קג", "ק\"ג", "מ\"ל", "מל", "ליטר", "מארז"]

def normalize_name(s: str) -> str:
    s = str(s).lower().strip()
    s = re.sub(r"[\u200e\u200f\u202a-\u202e]", "", s)
    s = re.sub(r"\d+(?:[.,]\d+)?", " ", s)
    for w in HEBREW_NOISE:
        s = s.replace(w, " ")
    s = re.sub(r"[^\w\u0590-\u05ff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def load_catalog(path: str | Path) -> pd.DataFrame:
    df = pd.read_json(path)
    df["match_key"] = df["name"].fillna("").map(normalize_name)
    return df

def read_basket(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(p)
    else:
        df = pd.read_csv(p)
    # Accept English/Hebrew-ish columns.
    candidates = ["name", "product", "item", "שם", "מוצר", "שם מוצר"]
    col = next((c for c in candidates if c in df.columns), df.columns[0])
    df = df.rename(columns={col: "input_name"})
    return df

def match_basket(basket: pd.DataFrame, catalog: pd.DataFrame, min_score: int = 70) -> pd.DataFrame:
    choices = catalog["match_key"].tolist()
    rows = []
    for _, item in basket.iterrows():
        q = normalize_name(item["input_name"])
        best = process.extractOne(q, choices, scorer=fuzz.WRatio) if q else None
        if not best or best[1] < min_score:
            rows.append({**item.to_dict(), "matched_name": None, "score": 0, "hahishook_price_nis": None, "product_url": None})
            continue
        _, score, idx = best
        prod = catalog.iloc[idx]
        rows.append({**item.to_dict(), "matched_name": prod["name"], "score": score, "hahishook_price_nis": prod.get("price_nis"), "size_text": prod.get("size_text"), "unit_price_text": prod.get("unit_price_text"), "product_url": prod.get("product_url")})
    return pd.DataFrame(rows)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("basket")
    ap.add_argument("--catalog", default="data/products.json")
    ap.add_argument("--out", default="data/basket_matches.csv")
    ap.add_argument("--min-score", type=int, default=70)
    args = ap.parse_args()
    catalog = load_catalog(args.catalog)
    basket = read_basket(args.basket)
    result = match_basket(basket, catalog, args.min_score)
    result.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"Wrote {args.out}")

if __name__ == "__main__":
    main()
