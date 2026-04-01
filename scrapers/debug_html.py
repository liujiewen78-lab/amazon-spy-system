"""Debug script to inspect Amazon BSR page HTML structure."""
import httpx
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import re
import json

ua = UserAgent()
headers = {
    'User-Agent': ua.random,
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

url = 'https://www.amazon.com/Best-Sellers-Sports-Outdoors/zgbs/sporting-goods/'
resp = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
soup = BeautifulSoup(resp.text, 'lxml')

items = soup.select('div.zg-grid-general-faceout')
print(f"Total items found: {len(items)}")

results = []
for item in items[:5]:
    parent = item.find_parent(attrs={'data-asin': True})
    asin = parent.get('data-asin', '') if parent else ''

    # Title from img alt
    title_el = item.select_one('img')
    title = title_el.get('alt', '') if title_el else ''

    # Price - try multiple selectors
    price_text = ''
    for sel in ['.p13n-sc-price', 'span.a-price .a-offscreen', '.a-price-whole', '.a-color-price']:
        el = item.select_one(sel)
        if el:
            price_text = el.get_text(strip=True)
            break

    # Rating
    rating_text = ''
    rating_el = item.select_one('.a-icon-alt')
    if rating_el:
        rating_text = rating_el.get_text(strip=True)

    # Review count
    review_text = ''
    for sel in ['.a-size-small .a-link-normal', 'span[aria-label]', '.a-size-base']:
        el = item.select_one(sel)
        if el:
            t = el.get_text(strip=True)
            if re.search(r'\d', t):
                review_text = t
                break

    # ASIN from link if not found
    if not asin:
        link_el = item.select_one('a[href*="/dp/"]')
        if link_el:
            m = re.search(r'/dp/([A-Z0-9]{10})', link_el.get('href', ''))
            asin = m.group(1) if m else ''

    result = {
        'asin': asin,
        'title': title[:80],
        'price_raw': price_text,
        'rating_raw': rating_text,
        'review_raw': review_text,
    }
    results.append(result)
    print(json.dumps(result, ensure_ascii=False))

# Also show raw HTML of first item for selector debugging
if items:
    print("\n=== FIRST ITEM HTML (first 1500 chars) ===")
    print(str(items[0])[:1500])
