"""
浏览器采集入口 — 本地运行版
用 Playwright 控制 Chromium 真实浏览器抓取 Amazon，绕过反爬。
运行方式: py -3.14 scrapers/main_browser.py
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_scraper import run_browser_scrape

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('scrape.log', encoding='utf-8'),
    ]
)
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / 'config' / 'rules.json'
DATA_DIR = BASE_DIR / 'data'
SNAPSHOTS_DIR = DATA_DIR / 'snapshots'

# 全部13个类目 — 全量模式
ALL_CATEGORIES = [
    'Kitchen & Dining',
    'Home & Garden',
    'Sports & Outdoors',
    'Tools & Home Improvement',
    'Pet Supplies',
    'Office Products',
    'Arts, Crafts & Sewing',
    'Automotive',
    'Beauty & Personal Care',
    'Toys & Games',
    'Travel & Luggage',
    'Home Improvement',
    'Patio & Garden',
]

MAX_ENRICH = 30  # 每次最多精细分析30个产品

def main():
    with open(CONFIG_PATH) as f:
        config = json.load(f)

    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H')
    log.info(f'=== Amazon Spy 浏览器采集开始 {timestamp} ===')
    log.info(f'类目数: {len(ALL_CATEGORIES)}, 最大enrichment: {MAX_ENRICH}')
    log.info('浏览器窗口将自动打开，请勿关闭...')

    # headless=False → 显示浏览器窗口（本地运行推荐，更难被Amazon识别）
    # headless=True  → 无头模式（GitHub Actions用）
    import os
    is_ci = os.environ.get('CI') == 'true' or os.environ.get('GITHUB_ACTIONS') == 'true'
    enriched = run_browser_scrape(config, ALL_CATEGORIES, max_enrich=MAX_ENRICH, headless=is_ci)

    # 保存原始数据
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = SNAPSHOTS_DIR / f'{timestamp}_raw.json'
    with open(raw_path, 'w', encoding='utf-8') as f:
        json.dump({
            'scraped_at': datetime.now(timezone.utc).isoformat(),
            'total_candidates': len(enriched),
            'products': enriched,
        }, f, ensure_ascii=False, indent=2)

    log.info(f'原始数据已保存: {raw_path} ({len(enriched)} 个产品)')
    log.info('下一步: py -3.14 analyzer/main.py')
    log.info('=== 采集完成 ===')

if __name__ == '__main__':
    main()
