.PHONY: refresh refresh-fast weekly-refresh health install-automation test lint

# Regenerate every finding/chart/export from current data. See
# scripts/refresh_all.py for what this actually runs and why.
refresh:
	.venv/bin/python scripts/refresh_all.py

# Same, but skips the slow CSV/XLSX exports (data/exports/) — use when you
# just want the docs/images refreshed quickly.
refresh-fast:
	.venv/bin/python scripts/refresh_all.py --skip-exports

# What the Monday job does: reload static data, regenerate everything in a
# separate worktree, open a PR. Add ARGS=--no-pr to stop short of GitHub.
weekly-refresh:
	.venv/bin/python scripts/weekly_refresh.py $(ARGS)

# Is live data still arriving? (prints only; the scheduled job notifies)
health:
	.venv/bin/python scripts/health_check.py --print

# Schedule the health check (every 15 min) + weekly refresh (Mon 06:00).
install-automation:
	scripts/install_automation.sh

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check .
