.PHONY: refresh refresh-fast test lint

# Regenerate every finding/chart/export from current data. See
# scripts/refresh_all.py for what this actually runs and why.
refresh:
	.venv/bin/python scripts/refresh_all.py

# Same, but skips the slow CSV/XLSX exports (data/exports/) — use when you
# just want the docs/images refreshed quickly.
refresh-fast:
	.venv/bin/python scripts/refresh_all.py --skip-exports

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check .
