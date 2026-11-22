# Israeli Grocery Catalog

A multi-source grocery price catalog for Israel. Pulls product data from:

| Source | How | Volume per run |
| --- | --- | --- |
| **hahishook.com** (Hahishook co-op) | HTML scraper of the public WooCommerce storefront | ~600 SKUs |
| **prices.shufersal.co.il** (Shufersal) | Official price-transparency XML feed (per store) | ~6,000+ SKUs per store |
| _(more chains coming &mdash; the transparency feeds are mandated by law for every chain over a certain size, same XML schema)_ | | |

Outputs a unified `data/products.json|csv|sqlite` catalog, serves it via a
FastAPI search backend, ships a tiny static interactive site to GitHub Pages,
and exposes the data to AI assistants via an MCP server.

Open the [public Hahishook catalog](https://idocohn.github.io/shopping-helper/)
on your phone or computer to browse and search without installing anything.
Open **Compare a basket** to import a Shufersal text PDF, submit a receipt
photo or other text receipt to AI, or enter items by hand. The screen compares covered items
and estimated prices from the Hahishook and Shufersal store 003 snapshots.
The results table shows product photos where available, match status, and
savings against the receipt's paid line price or a verified Shufersal price.
It opens on rows with positive savings and automatically selects good matches
that cost less. Similar products show their differences for review.
Use **Add to basket** on the Hahishook products you want, then review or edit
pack quantities before continuing to Hahishook. The checkout link sends only
product IDs and quantities. Hahishook confirms final prices and places the order.
For AI actions, enter an OpenAI API key. The browser uses it for that action,
sends it directly to OpenAI, and clears the field. For scanned PDFs, upload a
photo of the receipt or paste the item lines.

To preview the public site locally, run `npm ci --prefix mcp_server --omit=optional`,
`python build_pages.py --owner idocohn --repo shopping-helper`, and
`python -m http.server 8080 --directory _site`.

## What's in the box

```text
sources/
  shufersal.py    Pulls latest PriceFull XML per store from the transparency portal
scraper/          (Hahishook-specific) Async httpx + BeautifulSoup crawler
  discover.py       Walks the site to find every /product-category/ URL
  scrape.py         Paginates each category and extracts product cards
  models.py         Pydantic Product schema (shared across sources)
  utils.py          URL + price helpers, browser-like HTTP headers
build_catalog.py  Orchestrator: runs every source, merges, writes data/*
matching/
  match_basket.py rapidfuzz-based basket -> catalog matcher (CSV/XLSX)
backend/
  app.py          FastAPI server with cached catalog + search endpoints
webapp/         Vite + React UI (search, category filter, basket upload)
mcp_server/     MCP stdio server + GitHub Pages landing page template
tests/
  smoke_check.py  Stdlib-only sanity check that Hahishook selectors match
data/           Built catalog lands here (committed back by the nightly Action)
```

## Requirements

- Python 3.11+ (Windows or Unix)
- Node 22.12+ for the web UI (optional)
- Docker (optional, for `docker compose up`)

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
```

### Sanity-check (no install required)

```bash
python tests/smoke_check.py
```

Stdlib-only; confirms the live Hahishook HTML still uses the WooCommerce
class names the scraper relies on.

### Build the merged catalog

```bash
python build_catalog.py
```

This runs every configured source (Hahishook scraper + Shufersal feed),
tags each product with its `source`, dedupes within source, and writes:

```text
data/categories.json    list of discovered Hahishook category URLs
data/products.json      merged catalog as JSON (with `source` field)
data/products.csv       same, as UTF-8 BOM CSV (Excel-friendly)
data/catalog.sqlite     same, as a SQLite table called `products`
```

Useful options:

```bash
python build_catalog.py --only hahishook            # one source only
python build_catalog.py --only shufersal            # one source only
python build_catalog.py --only hahishook shufersal  # explicit list
```

By default, the command writes the sources that return products. Pass
`--preserve-existing` to retain the previous data for any failed or unselected
source. If every selected source fails, the existing catalog stays on disk.

### Adding a new source

1. Create `sources/<name>.py` with a `scrape(...) -> list[Product]` function
   that sets `source="<name>"` on every record it returns.
2. Add an entry to the `SOURCES` list in [build_catalog.py](build_catalog.py).
3. The workflow, API, and MCP tools use `source` from the data. The public
   GitHub Pages browser displays Hahishook products.

#### Chains worth adding (Israeli price-transparency portals)

Israeli law mandates that every grocery chain above a certain size publishes
daily price files. The schema is consistent (`PriceFull*.gz` -> XML with an
`<Items><Item>` tree), but each chain hosts on one of three different portal
platforms. Pick a chain, inspect its portal, copy [sources/shufersal.py](sources/shufersal.py)
as a starting point, swap the listing-URL function for the right platform.

Top-level gov directory of every legally-published portal:
[gov.il/he/pages/cpfta_shkifot_kishorim](https://www.gov.il/he/pages/cpfta_shkifot_kishorim).

| Platform | Portal | Status | What to copy from `shufersal.py` |
| --- | --- | --- | --- |
| **Cerberus / FileObject** (signed Azure Blob URLs, `?catID=2&storeId=N`) | [prices.shufersal.co.il](https://prices.shufersal.co.il/) | done | -- |
| **Direct date-folder** (no auth, `/YYYYMMDD/PriceFull...gz`) | [prices.carrefour.co.il](https://prices.carrefour.co.il/) | TODO | Replace `latest_price_full_url` with a small lister that walks the date folders. `_parse_xml` is reusable as-is. |
| **Laib catalog** (JS-rendered table, XHR-backed) | [laibcatalog.co.il/victory](https://laibcatalog.co.il/victory/index.html) | TODO | Find the XHR endpoint the page calls (DevTools Network tab). It typically returns JSON listing the GZ URLs. Replace `latest_price_full_url`; reuse `_parse_xml`. |
| **publishedprices.co.il** (Cerberus, login-walled, anonymous-friendly creds) | [Rami Levy](https://www.rami-levy.co.il/he/price-transparency) -> `url.retail.publishedprices.co.il/login` (user `RamiLevi`, blank password); also hosts Yochananof, Hatzi Hinam, Stop Market, others | TODO | Adds a login step: POST to `/login/user` to get a session cookie, then GET `/file/d/{filename}`. Stash creds in `os.environ`. |

Validation aggregators (good for sanity-checking, but **not** raw feeds &mdash;
don't scrape these as sources): [pricez.co.il](https://www.pricez.co.il/),
[israbis.com](https://israbis.com/en).

Ecommerce sites (Carrefour online, Shufersal online, Victory online) are
JS-heavy and exist behind the same brands &mdash; always prefer the price-file
portal above.

### Serve the catalog locally

```bash
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

Endpoints:

| Method | Path | What it returns |
| --- | --- | --- |
| GET | `/api/health` | `{ok, products, catalog_exists}` |
| GET | `/api/sources` | `[{source, count}, ...]` |
| GET | `/api/categories` | `[{category, count}, ...]` |
| GET | `/api/products` | `{total, items}` with filters `q`, `category`, `source`, `in_stock`, `min_price`, `max_price`, `limit`, `offset` |
| POST | `/api/match` | multipart `file` (CSV/XLSX/XLS basket, up to 5 MB and 1,000 rows), returns fuzzy matches against the catalog |

Example:

```bash
curl "http://localhost:8000/api/products?source=shufersal&q=%D7%98%D7%97%D7%99%D7%A0%D7%94&limit=10"
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

The matcher accepts CSV, XLSX, or XLS. The first column is treated as the
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

1. Runs `python build_catalog.py --preserve-existing` and keeps the previous
   snapshot for any source that fails. The run fails if no source returns products.
2. Builds the Pages site, commits the catalog files to `main`, and deploys
   the site. `manifest.json` reports product counts and actual scrape times.

GitHub pauses scheduled workflows in inactive public repositories. Re-enable
**Update catalog** from the Actions tab if its schedule is disabled. The
publish-only workflow also deploys committed catalog or site changes on `main`.

If GitHub Actions cannot reach a store, refresh that store from a machine
with access and commit the regenerated catalog files. For Hahishook, run
`python build_catalog.py --only hahishook --preserve-existing`.

After the first successful run, the catalog is publicly available at

```text
https://<your-gh-user>.github.io/<your-repo>/products.json
https://<your-gh-user>.github.io/<your-repo>/categories.json
https://<your-gh-user>.github.io/<your-repo>/manifest.json
```

One-time setup in the GitHub repo:

1. Settings &rarr; Pages &rarr; Source: **GitHub Actions**.
2. Run **Publish catalog to Pages** from the Actions tab to publish the
   committed snapshot. Run **Update catalog** to fetch fresh prices.

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
