"""调试真实页面HTML结构，找到正确的产品卡片selector"""
from playwright.sync_api import sync_playwright
import time, json

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        executable_path=CHROME_PATH,
        headless=False,
        slow_mo=100,
        args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
    )
    context = browser.new_context(
        viewport={'width': 1440, 'height': 900},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        locale='en-US',
    )
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
    page = context.new_page()

    page.goto('https://www.amazon.com/gp/movers-and-shakers/', wait_until='domcontentloaded', timeout=25000)
    time.sleep(4)

    # 找 data-asin 的父容器结构
    result = page.evaluate("""
    () => {
        const items = document.querySelectorAll('[data-asin]');
        const out = [];
        for (let item of Array.from(items).slice(0, 3)) {
            // Walk up to find meaningful container
            let el = item;
            const info = {
                asin: item.dataset.asin,
                tagName: item.tagName,
                className: item.className.substring(0, 80),
                // Get all text content fragments
                texts: [],
                imgAlts: [],
                innerHTMLSnippet: item.innerHTML.substring(0, 600)
            };
            // Find all text nodes
            const walker = document.createTreeWalker(item, NodeFilter.SHOW_TEXT);
            let node;
            while (node = walker.nextNode()) {
                const t = node.textContent.trim();
                if (t && t.length > 1) info.texts.push(t);
            }
            // Find all img alts
            item.querySelectorAll('img').forEach(img => {
                if (img.alt) info.imgAlts.push(img.alt.substring(0, 80));
            });
            out.push(info);
        }
        return out;
    }
    """)

    for item in result:
        print(f"ASIN: {item['asin']}")
        print(f"Tag: {item['tagName']}, Class: {item['className']}")
        print(f"Texts: {item['texts'][:8]}")
        print(f"ImgAlts: {item['imgAlts'][:3]}")
        print(f"HTML: {item['innerHTMLSnippet'][:300]}")
        print("---")

    browser.close()
