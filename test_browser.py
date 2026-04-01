"""快速验证：用真实Chrome抓取Movers&Shakers，打印前5个产品"""
import sys
sys.path.insert(0, 'scrapers')
from playwright.sync_api import sync_playwright
from browser_scraper import _parse_bsr_products, _human_delay
import time

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        executable_path=CHROME_PATH,
        headless=False,
        slow_mo=80,
        args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
    )
    context = browser.new_context(
        viewport={'width': 1440, 'height': 900},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        locale='en-US',
    )
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
    page = context.new_page()

    print('访问 Movers & Shakers...')
    page.goto('https://www.amazon.com/gp/movers-and-shakers/', wait_until='domcontentloaded', timeout=25000)
    time.sleep(3)

    products = _parse_bsr_products(page, 'movers_shakers')
    print(f'\n找到 {len(products)} 个产品:\n')
    for p in products[:8]:
        print(f"ASIN: {p['asin']}  Price: ${p['price']:.2f}  Rating: {p['rating']}  Reviews: {p['review_count']}")
        print(f"  {p['title'][:65]}")
        print()

    time.sleep(2)
    browser.close()
    print('完成！')
