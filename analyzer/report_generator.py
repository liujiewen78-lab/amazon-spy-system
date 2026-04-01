"""
Report Generator — Copies latest report to docs/ for GitHub Pages.
Also generates a lightweight summary for the status page.
"""

import json
import shutil
import logging
from pathlib import Path
from datetime import datetime, timezone

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = BASE_DIR / "docs"


def run():
    latest_path = DATA_DIR / "latest.json"
    if not latest_path.exists():
        log.warning("No latest.json found, skipping report generation")
        return

    # Ensure docs/data exists and is accessible
    docs_data = DOCS_DIR / "data"
    docs_data.mkdir(exist_ok=True)

    # Copy data directory to docs for GitHub Pages to serve
    data_snapshots = DATA_DIR / "snapshots"
    docs_snapshots = docs_data / "snapshots"
    docs_snapshots.mkdir(exist_ok=True)

    # Copy latest.json
    shutil.copy2(latest_path, docs_data / "latest.json")
    log.info("Copied latest.json to docs/data/")

    # Copy index.json
    index_path = DATA_DIR / "index.json"
    if index_path.exists():
        shutil.copy2(index_path, docs_data / "index.json")
        log.info("Copied index.json to docs/data/")

    # Copy recent snapshots (last 48 hours = 48 files)
    snapshot_files = sorted(data_snapshots.glob("*_report.json"), reverse=True)[:48]
    for sf in snapshot_files:
        dest = docs_snapshots / sf.name
        shutil.copy2(sf, dest)
    log.info(f"Copied {len(snapshot_files)} snapshot files to docs/data/snapshots/")

    log.info("Report generation complete.")


if __name__ == "__main__":
    run()
