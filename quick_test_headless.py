"""快速headless测试：采集2个类目 + 分析完整链路"""
import sys, json, logging
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, 'scrapers')

# 临时让browser_scraper用headless模式
import scrapers.browser_scraper as bs_module
_orig_run = bs_module.run_browser_scrape

def _patched_run(config, categories, max_enrich=5):
    """Same as original but headless=True for CI/subprocess compatibility"""
    from playwright.sync_api import sync_playwright
    import random, time, logging as _log
    log = _log.getLogger('browser_scraper')
    all_products = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            slow_mo=30,
            args=['--disable-blink-features=AutomationControlled','--no-sandbox','--disable-dev-shm-usage']
        )
        context = browser.new_context(
            viewport={'width': 1366, 'height': 768},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            locale='en-US',
        )
        context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        page = context.new_page()

        from scrapers.browser_scraper import (
            MOVERS_URL, NEW_RELEASES_URL, BSR_CATEGORY_URLS,
            _parse_bsr_products, _human_delay, _apply_hard_filters,
            _build_keyword, _scrape_search_top10, _scrape_reviews
        )

        # Movers
        log.info('Scraping Movers & Shakers (headless)...')
        try:
            page.goto(MOVERS_URL, wait_until='domcontentloaded', timeout=20000)
            time.sleep(2)
            products = _parse_bsr_products(page, 'movers_shakers')
            log.info(f'  -> {len(products)} products')
            all_products.extend(products)
        except Exception as e:
            log.warning(f'Movers failed: {e}')

        # BSR categories
        for cat in categories:
            url = BSR_CATEGORY_URLS.get(cat)
            if not url:
                continue
            log.info(f'Scraping BSR: {cat}...')
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=20000)
                time.sleep(2)
                products = _parse_bsr_products(page, f'bsr_{cat.lower().replace(" ", "_")}')
                log.info(f'  -> {len(products)} products')
                all_products.extend(products)
            except Exception as e:
                log.warning(f'BSR {cat} failed: {e}')
            time.sleep(2)

        # Dedup
        seen = set()
        deduped = []
        for p in all_products:
            if p.get('asin') and p['asin'] not in seen:
                seen.add(p['asin'])
                deduped.append(p)
        log.info(f'After dedup: {len(deduped)} unique products')

        # Hard filters
        filtered = _apply_hard_filters(deduped, config['hard_exclusions'])
        log.info(f'After hard filters: {len(filtered)} products')

        # Enrichment (competitors + reviews)
        enriched = []
        limit = min(max_enrich, len(filtered))
        log.info(f'Enriching top {limit} products...')
        for i, product in enumerate(filtered[:limit]):
            log.info(f'  [{i+1}/{limit}] {product["asin"]} - {product["title"][:45]}')
            keyword = _build_keyword(product['title'])
            product['keyword'] = keyword
            if keyword:
                competitors = _scrape_search_top10(page, keyword)
                product['competitors_top10'] = competitors
                log.info(f'    competitors: {len(competitors)}')
                time.sleep(2)
            reviews = _scrape_reviews(page, product['asin'], max_reviews=10)
            product['reviews_sample'] = reviews
            log.info(f'    reviews: {len(reviews)}')
            enriched.append(product)
            time.sleep(2)

        browser.close()
    return enriched

bs_module.run_browser_scrape = _patched_run

from browser_scraper import run_browser_scrape

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
with open(BASE_DIR / 'config' / 'rules.json') as f:
    config = json.load(f)

log.info('=== 快速headless测试 ===')
result = _patched_run(config, ['Sports & Outdoors', 'Pet Supplies'], max_enrich=3)

# 保存到latest_raw供分析用
snap_dir = BASE_DIR / 'data' / 'snapshots'
snap_dir.mkdir(parents=True, exist_ok=True)
ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H')
raw_path = snap_dir / f'{ts}_quick_raw.json'
with open(raw_path, 'w', encoding='utf-8') as f:
    json.dump({'scraped_at': datetime.now(timezone.utc).isoformat(), 'products': result}, f, ensure_ascii=False, indent=2)

log.info(f'保存 {len(result)} 个产品 -> {raw_path}')
for p in result[:5]:
    print(f"  {p['asin']} | ${p['price']} | {p['rating']}★ | competitors={len(p.get('competitors_top10',[]))} | reviews={len(p.get('reviews_sample',[]))}")
    print(f"    {p['title'][:70]}")
