install:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

discover:
	python -m scraper.discover

scrape:
	python -m scraper.scrape --categories data/categories.json --outdir data

scrape-all:
	python -m scraper.scrape --discover --outdir data

test-scrape:
	python -m scraper.scrape --limit 2 --outdir data

smoke:
	python tests/smoke_check.py

api:
	uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

mcp:
	python -m mcp_server.server
