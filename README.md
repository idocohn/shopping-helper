# Hahishook Switcher

A starter toolkit for building a cheaper-grocery comparison around
[hahishook.com](https://hahishook.com). It scrapes the public WooCommerce
catalog, stores it locally (JSON + CSV + SQLite), serves it over a small
FastAPI search backend, and ships a tiny React UI plus a basket-matching CLI.

## What's in the box

```text
scraper/        Async httpx + BeautifulSoup crawler
  discover.py     Walks the site to find every /product-category/ URL
  scrape.py       Paginates each category and extracts product cards
  models.py       Pydantic Product schema
  utils.py        URL + price helpers
matching/
  match_basket.py rapidfuzz-based basket -> catalog matcher (CSV/XLSX)
backend/
  app.py          FastAPI server with cached catalog + search endpoints
webapp/         Vite + React UI (search, category filter, basket upload)
mcp_server/     MCP stdio server for AI assistants (Claude Desktop, Cursor, ...)
tests/
  smoke_check.py  Stdlib-only sanity check that the live site selectors match
data/           Scraped outputs land here (gitignored content)
```

## Requirements

- Python 3.11+ (Windows or Unix)
- Node 20+ for the web UI (optional)
- Docker (optional, for `docker compose up`)

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
```

### Sanity-check the site selectors (no install required)

```bash
python tests/smoke_check.py
```

This uses only the Python stdlib and confirms that the live Hahishook HTML
still uses the WooCommerce class names the scraper relies on.

### Scrape the whole site

```bash
python -m scraper.scrape --discover
```

This walks the site to find every category, then paginates each one and
writes:

```text
data/categories.json    list of every discovered category URL
data/products.json      full catalog as JSON
data/products.csv       same, as UTF-8 BOM CSV (Excel-friendly)
data/catalog.sqlite     same, as a SQLite table called `products`
```

If you already have `data/categories.json`, just run `python -m scraper.scrape`
and it will reuse it. Pass `--limit N` to scrape only the first N categories
while iterating.

### Serve the catalog

```bash
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

Endpoints:

| Method | Path              | What it returns                                                                 |
| ------ | ----------------- | ------------------------------------------------------------------------------- |
| GET    | `/api/health`     | `{ok, products, catalog_exists}`                                                |
| GET    | `/api/categories` | `[{category, count}, …]` sorted by count                                        |
| GET    | `/api/products`   | `{total, items}` with filters `q`, `category`, `in_stock`, `min_price`, `max_price`, `limit`, `offset` |
| POST   | `/api/match`      | multipart `file` (CSV/XLSX basket), returns fuzzy matches against the catalog   |

Example:

```bash
curl "http://localhost:8000/api/products?q=%D7%98%D7%97%D7%99%D7%A0%D7%94&limit=10"
```

### Run the web UI

```bash
cd webapp
npm install
npm run dev
```

Then open <http://localhost:5173>. The page reads `VITE_API_URL` (default
`http://localhost:8000`).

### Docker Compose

```bash
docker compose up --build
```

This brings up the API on :8000 and the Vite dev server on :5173. The
`data/` folder is bind-mounted so re-running the scraper on the host
immediately updates what the API serves.

## Basket matching CLI

The matcher accepts a CSV or XLSX. The first column is treated as the
product name, or you can use any of these column names:

`name`, `product`, `item`, `שם`, `מוצר`, `שם מוצר`

```bash
python -m matching.match_basket my_basket.csv \
  --catalog data/products.json \
  --out data/basket_matches.csv \
  --min-score 70
```

## Nightly refresh + public catalog on GitHub Pages

[.github/workflows/update-catalog.yml](.github/workflows/update-catalog.yml)
runs once a day (cron `0 3 * * *`, also `workflow_dispatch`). It:

1. Installs deps and runs `python -m scraper.scrape --discover`.
2. Commits the regenerated `data/*.json|csv|sqlite` back to `main`.
3. Builds a tiny `_site/` containing `products.json`, `categories.json`,
   a `manifest.json` with `{count, updated_at}`, and a personalized
   `index.html` landing page, then deploys it to GitHub Pages.

After the first successful run, the catalog is publicly available at

```text
https://<your-gh-user>.github.io/<your-repo>/products.json
https://<your-gh-user>.github.io/<your-repo>/categories.json
https://<your-gh-user>.github.io/<your-repo>/manifest.json
```

One-time setup in the GitHub repo:

1. Settings &rarr; Pages &rarr; Source: **GitHub Actions**.
2. Run the `Update catalog` workflow once manually from the Actions tab.

## MCP server for AI assistants

`mcp_server/server.py` is a stdio MCP server that points at the public
catalog URL and exposes four tools to any MCP-aware AI client:

| Tool                | Purpose                                                   |
| ------------------- | --------------------------------------------------------- |
| `search_products`   | Query by free text + filters (category, price, in-stock). |
| `list_categories`   | All categories with product counts.                       |
| `get_product`       | Fetch one product by its hahishook.com URL.               |
| `catalog_info`      | Metadata: source URL, count, fetched-at, TTL.             |

Run it locally:

```bash
pip install -r requirements.txt
HAHISHOOK_CATALOG_URL="https://<your-gh-user>.github.io/<your-repo>/products.json" \
  python -m mcp_server.server
```

### Wiring it into Claude Desktop

Edit `claude_desktop_config.json` (macOS:
`~/Library/Application Support/Claude/`, Windows:
`%APPDATA%\Claude\`) and add:

```jsonc
{
  "mcpServers": {
    "hahishook": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "C:/path/to/shopping-helper",
      "env": {
        "HAHISHOOK_CATALOG_URL": "https://<your-gh-user>.github.io/<your-repo>/products.json"
      }
    }
  }
}
```

Same shape works for Cursor, Continue, Zed, and other MCP clients - they
all accept a `command`/`args`/`env` tuple. Restart the client and you'll
see the four tools appear under the `hahishook` server.

### Local-file mode (offline)

Set `HAHISHOOK_CATALOG_URL` to a `file://` URL to point at a locally
scraped catalog, e.g.

```text
file:///C:/path/to/shopping-helper/data/products.json
```

## Notes and caveats

- Hahishook varies stock and price by delivery warehouse. The scraper hits
  the default warehouse the site picks for anonymous visitors. If you need
  another warehouse's view you'll have to drive a real browser session
  (Playwright would be the natural extension).
- Pagination is generated from the `last page` link in WooCommerce's nav,
  so every page of a category is fetched, not only the page-1 neighbours.
- `price_to_float` and the size/unit-price extractors are heuristics tuned
  to the current Hebrew markup. If the storefront theme changes, run
  `python tests/smoke_check.py` first to see if selectors still match.
- The basket matcher is fuzzy on names only. It doesn't yet normalize
  pack sizes (e.g. "1 ק״ג" vs "500 גרם x 2"), so treat low-score matches
  as suggestions.
- Only public catalog pages are scraped. Don't point this at logged-in or
  private endpoints without permission.
