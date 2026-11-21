import asyncio
from collections import Counter
from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app import app
from build_catalog import build
from build_pages import build_pages
from scraper.models import Product
from scraper.scrape import parse_product_cards


class CatalogTests(unittest.TestCase):
    def test_product_card_uses_sale_price_and_ignores_nested_link(self):
        html = """
        <li class="product post-123 outofstock">
          <a href="?add-to-cart=123">Add to cart</a>
          <a class="woocommerce-LoopProduct-link" href="/product/almonds/">
            <h2>Almonds</h2>
          </a>
          <h5 class="product-subtitle">500 גרם</h5>
          <span class="price">
            <del><span class="woocommerce-Price-amount">₪20</span></del>
            <ins><span class="woocommerce-Price-amount">₪15</span></ins>
          </span>
        </li>
        """
        products = parse_product_cards(html, "https://hahishook.com/", "Nuts")
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].price_nis, 15)
        self.assertEqual(products[0].size_text, "500 גרם")
        self.assertEqual(products[0].product_id, "123")
        self.assertEqual(products[0].product_url, "https://hahishook.com/product/almonds/")
        self.assertFalse(products[0].in_stock)

    def test_partial_refresh_preserves_source_and_its_snapshot_date(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            catalog = data / "products.json"
            old = Product(name="Old price", scraped_at="2026-06-28T19:34:46+00:00")
            fresh = Product(source="shufersal", name="New price", scraped_at="2026-11-21T07:00:00+00:00")
            catalog.write_text(json.dumps([old.model_dump()]), encoding="utf-8")
            (data / "categories.json").write_text("[]", encoding="utf-8")
            sources = [("hahishook", list, False), ("shufersal", lambda: [fresh], False)]
            with patch("build_catalog.SOURCES", sources):
                asyncio.run(build(data, preserve_existing=True))

            rows = json.loads(catalog.read_text(encoding="utf-8"))
            self.assertEqual(Counter(row["source"] for row in rows), {"hahishook": 1, "shufersal": 1})
            build_pages(data, root / "site", "idocohn", "shopping-helper")
            manifest = json.loads((root / "site" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(datetime.fromisoformat(manifest["source_updated_at"]["hahishook"]), datetime.fromisoformat(old.scraped_at))
            self.assertEqual(datetime.fromisoformat(manifest["updated_at"]), datetime.fromisoformat(fresh.scraped_at))

            before = catalog.read_bytes()
            with patch("build_catalog.SOURCES", [("hahishook", list, False)]):
                with self.assertRaises(SystemExit):
                    asyncio.run(build(data))
            self.assertEqual(catalog.read_bytes(), before)


class BasketTests(unittest.TestCase):
    def test_search_and_parse_baskets(self):
        with TestClient(app) as client:
            search = client.get("/api/products", params={"q": "טחינה", "limit": 1})
            self.assertGreater(search.json()["total"], 0)
            name = search.json()["items"][0]["name"]
            sheet = Workbook()
            sheet.active.append(["שם"])
            sheet.active.append([name])
            xlsx = BytesIO()
            sheet.save(xlsx)

            for filename, contents in [("basket.csv", f"name\n{name}\n".encode()), ("basket.xlsx", xlsx.getvalue())]:
                with self.subTest(filename=filename):
                    response = client.post("/api/match", files={"file": (filename, contents)})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()[0]["input_name"], name)
                    self.assertIn(response.json()[0]["matched_source"], {"hahishook", "shufersal"})
            invalid = client.post("/api/match", files={"file": ("basket.xlsx", b"not a spreadsheet")})
            self.assertEqual(invalid.status_code, 400)


if __name__ == "__main__":
    unittest.main()
