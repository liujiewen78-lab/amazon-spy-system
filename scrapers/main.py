"""
Amazon Spy System — Main Scraper Entry Point
Runs every hour via GitHub Actions. Scrapes Amazon US for product opportunities.
"""

import json
import time
import random
import logging
from datetime import datetime, timezone
from pathlib import Path

from amazon_scraper import AmazonScraper
from trends_scraper import TrendsScraper

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config" / "rules.json"
DATA_DIR = BASE_DIR / "data"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def run():
    config = load_config()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    log.info(f"Starting scrape run: {timestamp}")

    scraper = AmazonScraper(config)
    trends = TrendsScraper(config)

    raw_products = []

    # 1. Scan Movers & Shakers (highest signal for trending products)
    log.info("Scraping Movers & Shakers...")
    movers = scraper.scrape_movers_and_shakers()
    raw_products.extend(movers)

    # 2. Scan New Releases
    log.info("Scraping New Releases...")
    new_releases = scraper.scrape_new_releases()
    raw_products.extend(new_releases)

    # 3. Scan BSR top categories
    log.info("Scraping BSR categories...")
    bsr = scraper.scrape_bsr_categories(config["categories_to_scan"])
    raw_products.extend(bsr)

    # 4. Deduplicate by ASIN
    seen = set()
    deduped = []
    for p in raw_products:
        if p.get("asin") and p["asin"] not in seen:
            seen.add(p["asin"])
            deduped.append(p)
    log.info(f"Collected {len(deduped)} unique products after dedup")

    # 5. Apply hard exclusion filters
    filtered = scraper.apply_hard_filters(deduped, config["hard_exclusions"])
    log.info(f"{len(filtered)} products passed hard filters")

    # 6. Enrich with search result data (Top 10 competitors per product)
    enriched = []
    for i, product in enumerate(filtered[:50]):  # limit to top 50 candidates
        log.info(f"Enriching {i+1}/{min(len(filtered),50)}: {product.get('asin')}")
        try:
            enriched_product = scraper.enrich_product(product)
            enriched.append(enriched_product)
        except Exception as e:
            log.warning(f"Failed to enrich {product.get('asin')}: {e}")
        time.sleep(random.uniform(
            config["scraping"]["delay_min_seconds"],
            config["scraping"]["delay_max_seconds"]
        ))

    # 7. Save raw enriched data
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = SNAPSHOTS_DIR / f"{timestamp}_raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump({
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "total_candidates": len(enriched),
            "products": enriched
        }, f, ensure_ascii=False, indent=2)

    log.info(f"Raw data saved: {raw_path}")
    log.info("Scrape run complete.")

if __name__ == "__main__":
    run()
