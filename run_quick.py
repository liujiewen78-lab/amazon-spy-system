"""
快速验证模式 — 3个类目，max_enrich=5，验证完整链路
运行: py -3.14 run_quick.py
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, 'scrapers')
from browser_scraper import run_browser_scrape

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('scrape_quick.log', encoding='utf-8'),
    ]
)
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / 'config' / 'rules.json'
DATA_DIR = BASE_DIR / 'data'
SNAPSHOTS_DIR = DATA_DIR / 'snapshots'

# 只测3个类目
TEST_CATEGORIES = [
    'Kitchen & Dining',
    'Sports & Outdoors',
    'Pet Supplies',
]

MAX_ENRICH = 5  # 快速测试只精分5个

def main():
    with open(CONFIG_PATH) as f:
        config = json.load(f)

    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H')
    log.info(f'=== Amazon Spy 快速测试 {timestamp} ===')
    log.info(f'类目: {TEST_CATEGORIES}, max_enrich={MAX_ENRICH}')

    enriched = run_browser_scrape(config, TEST_CATEGORIES, max_enrich=MAX_ENRICH)

    # 保存
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = SNAPSHOTS_DIR / f'{timestamp}_quick_raw.json'
    with open(raw_path, 'w', encoding='utf-8') as f:
        json.dump({
            'scraped_at': datetime.now(timezone.utc).isoformat(),
            'mode': 'quick_test',
            'total_candidates': len(enriched),
            'products': enriched,
        }, f, ensure_ascii=False, indent=2)

    log.info(f'原始数据已保存: {raw_path} ({len(enriched)} 个产品)')

    # 直接运行分析
    import subprocess
    log.info('=== 开始分析 ===')
    r = subprocess.run([sys.executable, 'analyzer/main.py'], cwd=str(BASE_DIR))
    if r.returncode != 0:
        log.error('分析失败')
        sys.exit(1)

    log.info('=== 生成报告 ===')
    r = subprocess.run([sys.executable, 'analyzer/report_generator.py'], cwd=str(BASE_DIR))
    if r.returncode != 0:
        log.error('报告生成失败')
        sys.exit(1)

    log.info('')
    log.info('✅ 完整链路跑通！')
    log.info('查看报告: py -3.14 show_report.py')
    log.info('可视化: 用浏览器打开 docs/index.html')

if __name__ == '__main__':
    main()
