"""
Browser-based Amazon scraper using Playwright.
模拟真实用户浏览，绕过反爬机制。
"""

import re
import time
import random
import logging
import json
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, Browser, TimeoutError as PWTimeout

log = logging.getLogger(__name__)

BSR_CATEGORY_URLS = {
    "Kitchen & Dining":        "https://www.amazon.com/Best-Sellers-Kitchen-Dining/zgbs/kitchen/",
    "Home & Garden":           "https://www.amazon.com/Best-Sellers-Home-Garden/zgbs/garden/",
    "Sports & Outdoors":       "https://www.amazon.com/Best-Sellers-Sports-Outdoors/zgbs/sporting-goods/",
    "Tools & Home Improvement":"https://www.amazon.com/Best-Sellers-Tools-Home-Improvement/zgbs/hi/",
    "Pet Supplies":            "https://www.amazon.com/Best-Sellers-Pet-Supplies/zgbs/pet-supplies/",
    "Office Products":         "https://www.amazon.com/Best-Sellers-Office-Products/zgbs/office-products/",
    "Arts, Crafts & Sewing":   "https://www.amazon.com/Best-Sellers-Arts-Crafts-Sewing/zgbs/arts-and-crafts/",
    "Automotive":              "https://www.amazon.com/Best-Sellers-Automotive/zgbs/automotive/",
    "Beauty & Personal Care":  "https://www.amazon.com/Best-Sellers-Beauty/zgbs/beauty/",
    "Toys & Games":            "https://www.amazon.com/Best-Sellers-Toys-Games/zgbs/toys-and-games/",
    "Travel & Luggage":        "https://www.amazon.com/Best-Sellers-Luggage-Travel-Gear/zgbs/luggage/",
    "Home Improvement":        "https://www.amazon.com/Best-Sellers-Tools-Home-Improvement/zgbs/hi/",
    "Patio & Garden":          "https://www.amazon.com/Best-Sellers-Patio-Lawn-Garden/zgbs/lawn-garden/",
}

MOVERS_URL     = "https://www.amazon.com/gp/movers-and-shakers/"
NEW_RELEASES_URL = "https://www.amazon.com/gp/new-releases/"


def _human_delay(min_s=1.5, max_s=4.0):
    time.sleep(random.uniform(min_s, max_s))


def _parse_price(text: str) -> float:
    m = re.search(r'\$?([\d,]+\.?\d*)', text.replace(',', ''))
    return float(m.group(1)) if m else 0.0


def _parse_rating(text: str) -> float:
    m = re.search(r'([\d.]+)\s*out of', text)
    return float(m.group(1)) if m else 0.0


def _parse_reviews(text: str) -> int:
    clean = text.replace(',', '').replace('(', '').replace(')', '')
    m = re.search(r'\d+', clean)
    return int(m.group()) if m else 0


def _extract_asin(url: str) -> str:
    m = re.search(r'/dp/([A-Z0-9]{10})', url)
    return m.group(1) if m else ''


def _scroll_page(page: Page):
    """Slowly scroll down like a human."""
    for _ in range(3):
        page.mouse.wheel(0, random.randint(400, 800))
        time.sleep(random.uniform(0.3, 0.8))


def _parse_bsr_products(page: Page, source: str) -> list[dict]:
    """
    Extract product cards from BSR / Movers / New Releases page.
    Uses JS evaluate to parse [data-asin] containers directly — works with
    Amazon's 2024/2025 page structure where text nodes contain all data.
    """
    products = []
    try:
        # Wait for any data-asin element to appear
        page.wait_for_selector('[data-asin]', timeout=12000)
        _scroll_page(page)

        # Extract all data via JS in one call — fast and reliable
        raw_items = page.evaluate("""
        () => {
            const items = document.querySelectorAll('[data-asin]');
            const results = [];
            for (const item of items) {
                const asin = item.dataset.asin;
                if (!asin) continue;

                // Collect all text nodes
                const texts = [];
                const walker = document.createTreeWalker(item, NodeFilter.SHOW_TEXT);
                let node;
                while (node = walker.nextNode()) {
                    const t = node.textContent.trim();
                    if (t && t.length > 1) texts.push(t);
                }

                // Get product link
                const linkEl = item.querySelector('a[href*="/dp/"]');
                const href = linkEl ? linkEl.href : '';

                // Get img alt as title fallback
                const imgEl = item.querySelector('img[alt]');
                const imgAlt = imgEl ? imgEl.alt : '';

                results.push({ asin, texts, href, imgAlt });
            }
            return results;
        }
        """)

        for raw in raw_items:
            asin = raw.get('asin', '')
            texts = raw.get('texts', [])
            href = raw.get('href', '')
            img_alt = raw.get('imgAlt', '')

            if not asin:
                continue

            # Parse fields from text array
            title = ''
            price = 0.0
            rating = 0.0
            review_count = 0

            for t in texts:
                # Title: longest text that isn't a number/rank/price/label
                if (len(t) > 20 and not t.startswith('#') and '$' not in t
                        and 'out of' not in t and 'Sales rank' not in t
                        and 'previously' not in t and not t.isdigit()):
                    if not title or len(t) > len(title):
                        title = t

                # Price
                if '$' in t and not price:
                    p = _parse_price(t)
                    if p > 0:
                        price = p

                # Rating
                if 'out of 5' in t and not rating:
                    rating = _parse_rating(t)

                # Review count: pure number string (no $, no "out of")
                if (re.match(r'^[\d,]+$', t) and '$' not in t
                        and 'out of' not in t and len(t) <= 10 and not review_count):
                    rc = _parse_reviews(t)
                    if rc > 10:  # sanity check — avoid rank numbers
                        review_count = rc

            # Fallback title from img alt
            if not title and img_alt and len(img_alt) > 5:
                title = img_alt

            # ASIN from link if needed
            if not asin and href:
                asin = _extract_asin(href)

            if asin and title and len(title) > 5:
                products.append({
                    'asin': asin,
                    'title': title.strip(),
                    'price': price,
                    'rating': rating,
                    'review_count': review_count,
                    'source_page': source,
                    'platform': 'amazon_us',
                    'scraped_at': datetime.now(timezone.utc).isoformat(),
                })

    except PWTimeout:
        log.warning(f'Timeout waiting for products on {source}')
    except Exception as e:
        log.warning(f'Parse error on {source}: {e}')

    return products


def _scrape_search_top10(page: Page, keyword: str) -> list[dict]:
    """Scrape Top 10 search results for competitor analysis."""
    competitors = []
    try:
        url = f"https://www.amazon.com/s?k={keyword.replace(' ', '+')}"
        page.goto(url, wait_until='domcontentloaded', timeout=20000)
        _human_delay(2, 4)
        _scroll_page(page)

        raw_items = page.evaluate("""
        () => {
            const items = document.querySelectorAll('[data-asin][data-component-type="s-search-result"]');
            const results = [];
            for (const item of Array.from(items).slice(0, 10)) {
                const asin = item.dataset.asin;
                if (!asin) continue;

                const titleEl = item.querySelector('h2 span');
                const title = titleEl ? titleEl.textContent.trim() : '';

                const priceEl = item.querySelector('span.a-price .a-offscreen');
                const price = priceEl ? priceEl.textContent.trim() : '';

                const ratingEl = item.querySelector('.a-icon-alt');
                const rating = ratingEl ? ratingEl.textContent.trim() : '';

                const reviewEl = item.querySelector('.a-size-base.s-underline-text');
                const reviews = reviewEl ? reviewEl.textContent.trim() : '';

                const brandEl = item.querySelector('.a-size-base-plus.a-color-base, h2 + div span');
                const brand = brandEl ? brandEl.textContent.trim() : 'Unknown';

                const sponsored = !!item.querySelector('[aria-label="Sponsored"],.s-label-popover-default');

                results.push({ asin, title, price, rating, reviews, brand, sponsored });
            }
            return results;
        }
        """)

        for i, raw in enumerate(raw_items):
            asin = raw.get('asin', '')
            if not asin:
                continue
            competitors.append({
                'asin': asin,
                'title': raw.get('title', ''),
                'brand': raw.get('brand', 'Unknown'),
                'price': _parse_price(raw.get('price', '')),
                'rating': _parse_rating(raw.get('rating', '')),
                'review_count': _parse_reviews(raw.get('reviews', '')),
                'is_sponsored': raw.get('sponsored', False),
                'keyword': keyword,
                'search_rank': i + 1,
            })

    except Exception as e:
        log.warning(f'Search scrape failed for "{keyword}": {e}')

    return competitors


def _scrape_reviews(page: Page, asin: str, max_reviews: int = 30) -> list[dict]:
    """Scrape recent critical reviews using JS evaluate."""
    reviews = []
    try:
        url = f"https://www.amazon.com/product-reviews/{asin}?sortBy=recent&filterByStar=critical"
        page.goto(url, wait_until='domcontentloaded', timeout=20000)
        _human_delay(1.5, 3)

        raw_reviews = page.evaluate(f"""
        () => {{
            const items = document.querySelectorAll('[data-hook="review"]');
            const results = [];
            for (const rev of Array.from(items).slice(0, {max_reviews})) {{
                const ratingEl = rev.querySelector('[data-hook="review-star-rating"] .a-icon-alt');
                const bodyEl = rev.querySelector('[data-hook="review-body"] span');
                const titleEl = rev.querySelector('[data-hook="review-title"] span:not(.a-icon-alt)');
                results.push({{
                    rating: ratingEl ? ratingEl.textContent.trim() : '',
                    title: titleEl ? titleEl.textContent.trim() : '',
                    body: bodyEl ? bodyEl.textContent.trim().substring(0, 400) : '',
                }});
            }}
            return results;
        }}
        """)

        for raw in raw_reviews:
            reviews.append({
                'rating': _parse_rating(raw.get('rating', '')),
                'title': raw.get('title', ''),
                'body': raw.get('body', ''),
            })

    except Exception as e:
        log.warning(f'Reviews scrape failed for {asin}: {e}')

    return reviews


def _build_keyword(title: str) -> str:
    stop = {'for', 'with', 'and', 'the', 'a', 'an', 'of', 'to', 'in',
            'pack', 'set', 'pcs', 'piece', 'pieces', 'count', 'black', 'white', 'new'}
    words = re.findall(r'[a-zA-Z]+', title)
    filtered = [w.lower() for w in words if w.lower() not in stop and len(w) > 2]
    return ' '.join(filtered[:4])


def _apply_hard_filters(products: list[dict], exclusions: dict) -> list[dict]:
    filtered = []
    for p in products:
        title = (p.get('title') or '').lower()
        excluded = False
        for exc in exclusions['excluded_categories']:
            if exc.lower() in title:
                excluded = True
                break
        for kw in exclusions['excluded_keywords_in_title']:
            if kw.lower() in title:
                excluded = True
                break
        if p.get('price', 0) > exclusions.get('max_unit_cny', 500) / 7.2:
            excluded = True
        if not excluded:
            filtered.append(p)
    return filtered


CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def run_browser_scrape(config: dict, categories: list[str], max_enrich: int = 20,
                       headless: bool = False) -> list[dict]:
    """
    Main browser scrape entry point.
    Opens Chromium (or local Chrome if available), visits Amazon pages, returns enriched product list.
    headless=False → visible window (harder for Amazon to detect; default for local runs)
    headless=True  → background mode (for GitHub Actions / subprocess calls)
    """
    import os
    all_products = []
    chrome_exe = CHROME_PATH if os.path.exists(CHROME_PATH) else None

    with sync_playwright() as pw:
        log.info(f'Launching browser (headless={headless}, chrome={bool(chrome_exe)})...')
        launch_kwargs: dict = {
            'headless': headless,
            'slow_mo': 30 if headless else 50,
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ],
        }
        if chrome_exe:
            launch_kwargs['executable_path'] = chrome_exe
        browser = pw.chromium.launch(**launch_kwargs)

        context = browser.new_context(
            viewport={'width': 1366, 'height': 768},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
        )

        # 隐藏 webdriver 特征
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        page = context.new_page()

        # --- 1. Movers & Shakers ---
        log.info('Scraping Movers & Shakers...')
        try:
            page.goto(MOVERS_URL, wait_until='domcontentloaded', timeout=20000)
            _human_delay(2, 4)
            products = _parse_bsr_products(page, 'movers_shakers')
            log.info(f'  -> {len(products)} products')
            all_products.extend(products)
        except Exception as e:
            log.warning(f'Movers failed: {e}')

        _human_delay(2, 4)

        # --- 2. New Releases ---
        log.info('Scraping New Releases...')
        try:
            page.goto(NEW_RELEASES_URL, wait_until='domcontentloaded', timeout=20000)
            _human_delay(2, 4)
            products = _parse_bsr_products(page, 'new_releases')
            log.info(f'  -> {len(products)} products')
            all_products.extend(products)
        except Exception as e:
            log.warning(f'New Releases failed: {e}')

        _human_delay(2, 4)

        # --- 3. BSR Categories ---
        for cat in categories:
            url = BSR_CATEGORY_URLS.get(cat)
            if not url:
                continue
            log.info(f'Scraping BSR: {cat}...')
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=20000)
                _human_delay(2, 5)
                products = _parse_bsr_products(page, f'bsr_{cat.lower().replace(" ", "_")}')
                log.info(f'  -> {len(products)} products')
                all_products.extend(products)
            except Exception as e:
                log.warning(f'BSR {cat} failed: {e}')
            _human_delay(3, 6)

        # --- Dedup ---
        seen = set()
        deduped = []
        for p in all_products:
            if p.get('asin') and p['asin'] not in seen:
                seen.add(p['asin'])
                deduped.append(p)
        log.info(f'After dedup: {len(deduped)} unique products')

        # --- Hard filters ---
        filtered = _apply_hard_filters(deduped, config['hard_exclusions'])
        log.info(f'After hard filters: {len(filtered)} products')

        # --- Enrichment (search + reviews) ---
        enriched = []
        limit = min(max_enrich, len(filtered))
        log.info(f'Enriching top {limit} products...')

        for i, product in enumerate(filtered[:limit]):
            log.info(f'  [{i+1}/{limit}] {product["asin"]} - {product["title"][:45]}')
            keyword = _build_keyword(product['title'])
            product['keyword'] = keyword

            # Competitor search
            if keyword:
                competitors = _scrape_search_top10(page, keyword)
                product['competitors_top10'] = competitors
                log.info(f'    competitors: {len(competitors)}')
                _human_delay(2, 4)

            # Reviews
            reviews = _scrape_reviews(page, product['asin'])
            product['reviews_sample'] = reviews
            log.info(f'    reviews: {len(reviews)}')

            enriched.append(product)
            _human_delay(3, 6)

        browser.close()
        log.info('Browser closed.')

    return enriched
