"""
本地快速测试版采集脚本 — 只抓3个类目，限制enrichment数量，约2分钟跑完
正式部署用 main.py（GitHub Actions版）
"""

import json
import time
import random
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from amazon_scraper import AmazonScraper

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config" / "rules.json"
DATA_DIR = BASE_DIR / "data"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"

# 本地测试：只扫3个类目
TEST_CATEGORIES = [
    "Kitchen & Dining",
    "Sports & Outdoors",
    "Pet Supplies",
]

# 本地测试：enrichment只处理前10个产品
MAX_ENRICH = 10

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def run():
    config = load_config()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    log.info(f"[本地模式] 开始采集: {timestamp}")

    scraper = AmazonScraper(config)
    raw_products = []

    # 1. Movers & Shakers（最强信号）
    log.info("抓取 Movers & Shakers...")
    movers = scraper.scrape_movers_and_shakers()
    log.info(f"  → 拿到 {len(movers)} 个产品")
    raw_products.extend(movers)

    # 2. 精选3个类目BSR
    log.info(f"抓取 BSR（{len(TEST_CATEGORIES)} 个类目）...")
    bsr = scraper.scrape_bsr_categories(TEST_CATEGORIES)
    log.info(f"  → 拿到 {len(bsr)} 个产品")
    raw_products.extend(bsr)

    # 去重
    seen = set()
    deduped = []
    for p in raw_products:
        if p.get("asin") and p["asin"] not in seen:
            seen.add(p["asin"])
            deduped.append(p)
    log.info(f"去重后: {len(deduped)} 个产品")

    # 硬过滤
    filtered = scraper.apply_hard_filters(deduped, config["hard_exclusions"])
    log.info(f"过滤后: {len(filtered)} 个产品（过滤掉 {len(deduped)-len(filtered)} 个）")

    # Enrichment（本地只处理前10个）
    enriched = []
    limit = min(MAX_ENRICH, len(filtered))
    log.info(f"开始 enrichment（前 {limit} 个）...")
    for i, product in enumerate(filtered[:limit]):
        log.info(f"  [{i+1}/{limit}] {product.get('asin')} - {product.get('title','')[:40]}")
        try:
            enriched_product = scraper.enrich_product(product)
            enriched.append(enriched_product)
        except Exception as e:
            log.warning(f"  enrichment失败: {e}")
            enriched.append(product)
        time.sleep(random.uniform(2, 4))  # 本地模式延迟稍短

    # 保存
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = SNAPSHOTS_DIR / f"{timestamp}_raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump({
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "total_candidates": len(enriched),
            "products": enriched
        }, f, ensure_ascii=False, indent=2)

    log.info(f"原始数据已保存: {raw_path}")
    log.info(f"✅ 采集完成，共 {len(enriched)} 个产品进入分析阶段")
    log.info("下一步运行: py -3.14 analyzer/main.py")

if __name__ == "__main__":
    run()
