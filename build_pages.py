"""Build the static GitHub Pages site from a catalog snapshot."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil


def build_pages(data: Path, outdir: Path, owner: str, repo: str) -> None:
    products = json.loads((data / "products.json").read_text(encoding="utf-8"))
    if not products:
        raise ValueError("Cannot publish an empty product catalog")

    sources = Counter()
    source_times: dict[str, datetime] = {}
    for product in products:
        source = product.get("source") or "hahishook"
        sources[source] += 1
        try:
            scraped_at = datetime.fromisoformat(product.get("scraped_at") or "")
        except ValueError:
            continue
        if scraped_at.tzinfo is not None and (source not in source_times or scraped_at > source_times[source]):
            source_times[source] = scraped_at.astimezone(timezone.utc)

    latest = max(source_times.values(), default=None)
    manifest = {
        "count": len(products),
        "updated_at": latest.isoformat() if latest else None,
        "owner": owner,
        "repo": repo,
        "sources": dict(sources),
        "source_updated_at": {source: time.isoformat() for source, time in source_times.items()},
    }
    outdir.mkdir(parents=True, exist_ok=True)
    for name in ("products.json", "categories.json"):
        shutil.copyfile(data / name, outdir / name)
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    templates = Path(__file__).resolve().parent / "mcp_server"
    template = templates / "site_index.html"
    html = template.read_text(encoding="utf-8").replace("__OWNER__", owner).replace("__REPO__", repo)
    (outdir / "index.html").write_text(html, encoding="utf-8")
    shutil.copytree(templates / "basket", outdir / "basket", dirs_exist_ok=True)
    pdfjs = templates / "node_modules" / "pdfjs-dist"
    if pdfjs.exists():
        vendor = outdir / "basket" / "vendor"
        vendor.mkdir(exist_ok=True)
        for module in ("pdf", "pdf.worker"):
            shutil.copyfile(pdfjs / "legacy" / "build" / f"{module}.min.mjs", vendor / f"{module}.mjs")
        shutil.copyfile(pdfjs / "LICENSE", vendor / "LICENSE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--outdir", type=Path, default=Path("_site"))
    args = parser.parse_args()
    if not (Path(__file__).resolve().parent / "mcp_server" / "node_modules" / "pdfjs-dist").exists():
        parser.error("Run npm ci --prefix mcp_server --omit=optional before building the Pages site.")
    build_pages(args.data, args.outdir, args.owner, args.repo)
