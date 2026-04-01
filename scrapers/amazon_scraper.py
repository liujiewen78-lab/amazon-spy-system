"""
Amazon US Scraper
Scrapes BSR, New Releases, Movers & Shakers, Search Results, and Product Detail pages.
"""

import httpx
import time
import random
import re
import json
import logging
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential
from datetime import datetime, timezone

log = logging.getLogger(__name__)

HEADERS_BASE = {
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "DNT": "1",
}

EXCLUDED_CATEGORIES = [
    "Baby", "Infant", "Toddler", "Medical", "Health Device",
    "Grocery", "Food", "Beverage", "Ammunition", "Firearms"
]

BSR_CATEGORY_URLS = {
    "Kitchen & Dining": "https://www.amazon.com/Best-Sellers-Kitchen-Dining/zgbs/kitchen/",
    "Home & Garden": "https://www.amazon.com/Best-Sellers-Home-Garden/zgbs/garden/",
    "Sports & Outdoors": "https://www.amazon.com/Best-Sellers-Sports-Outdoors/zgbs/sporting-goods/",
    "Tools & Home Improvement": "https://www.amazon.com/Best-Sellers-Tools-Home-Improvement/zgbs/hi/",
    "Pet Supplies": "https://www.amazon.com/Best-Sellers-Pet-Supplies/zgbs/pet-supplies/",
    "Office Products": "https://www.amazon.com/Best-Sellers-Office-Products/zgbs/office-products/",
    "Arts, Crafts & Sewing": "https://www.amazon.com/Best-Sellers-Arts-Crafts-Sewing/zgbs/arts-and-crafts/",
    "Automotive": "https://www.amazon.com/Best-Sellers-Automotive/zgbs/automotive/",
    "Beauty & Personal Care": "https://www.amazon.com/Best-Sellers-Beauty/zgbs/beauty/",
    "Toys & Games": "https://www.amazon.com/Best-Sellers-Toys-Games/zgbs/toys-and-games/",
    "Travel Accessories": "https://www.amazon.com/Best-Sellers-Luggage-Travel-Gear/zgbs/luggage/",
}

MOVERS_URL = "https://www.amazon.com/gp/movers-and-shakers/"
NEW_RELEASES_URL = "https://www.amazon.com/gp/new-releases/"


class AmazonScraper:
    def __init__(self, config: dict):
        self.config = config
        self.ua = UserAgent()
        self.client = httpx.Client(
            timeout=config["scraping"]["timeout_seconds"],
            follow_redirects=True,
            headers=HEADERS_BASE
        )

    def _get_headers(self):
        return {**HEADERS_BASE, "User-Agent": self.ua.random}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=5, max=30))
    def _fetch(self, url: str) -> BeautifulSoup:
        resp = self.client.get(url, headers=self._get_headers())
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    def _extract_asin(self, url: str) -> str | None:
        match = re.search(r"/dp/([A-Z0-9]{10})", url)
        return match.group(1) if match else None

    def _parse_price(self, text: str) -> float | None:
        match = re.search(r"\$?([\d,]+\.?\d*)", text.replace(",", ""))
        return float(match.group(1)) if match else None

    def _parse_rating(self, text: str) -> float | None:
        match = re.search(r"([\d.]+)\s*out of\s*5", text)
        return float(match.group(1)) if match else None

    def _parse_review_count(self, text: str) -> int | None:
        match = re.search(r"([\d,]+)", text.replace(",", ""))
        return int(match.group(1)) if match else None

    def _parse_bsr_page(self, soup: BeautifulSoup, source: str) -> list[dict]:
        products = []
        # Amazon BSR 2024+ structure: div.zg-grid-general-faceout inside parent[data-asin]
        items = soup.select("div.zg-grid-general-faceout")
        if not items:
            items = soup.select("li.zg-item-immersion")

        for item in items[:30]:
            # ASIN: from parent container or link
            parent = item.find_parent(attrs={"data-asin": True})
            asin = parent.get("data-asin", "") if parent else ""
            if not asin:
                link = item.select_one("a[href*='/dp/']")
                if link:
                    asin = self._extract_asin(link.get("href", "")) or ""

            # Title: prefer div text, fallback to img alt
            title = ""
            title_div = item.select_one("div._cDEzb_p13n-sc-css-line-clamp-3_g3dy1, div._cDEzb_p13n-sc-css-line-clamp-4_2q2cc")
            if title_div:
                title = title_div.get_text(strip=True)
            if not title:
                img = item.select_one("img")
                title = img.get("alt", "") if img else ""

            # Price: try multiple selectors in priority order
            price = 0.0
            for sel in [".p13n-sc-price", "span.a-price .a-offscreen", ".a-color-price"]:
                el = item.select_one(sel)
                if el:
                    parsed = self._parse_price(el.get_text())
                    if parsed and parsed > 0:
                        price = parsed
                        break

            # Rating
            rating = 0.0
            rating_el = item.select_one(".a-icon-alt")
            if rating_el:
                rating = self._parse_rating(rating_el.get_text()) or 0.0

            # Review count: find aria-label with number pattern
            review_count = 0
            for sel in ["span[aria-label]", ".a-size-small span", ".a-size-base"]:
                for el in item.select(sel):
                    text = el.get_text(strip=True)
                    # review count looks like "1,234" or "(1234)" — not a price
                    if re.search(r'\d', text) and '$' not in text and 'out of' not in text:
                        parsed = self._parse_review_count(text)
                        if parsed and parsed > 0:
                            review_count = parsed
                            break
                if review_count:
                    break

            # Skip if no ASIN or no title
            if not asin or not title:
                continue

            products.append({
                "asin": asin,
                "title": title,
                "price": price,
                "rating": rating,
                "review_count": review_count,
                "source_page": source,
                "platform": "amazon_us",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            })
        return products

    def scrape_bsr_categories(self, categories: list[str]) -> list[dict]:
        products = []
        for cat in categories:
            url = BSR_CATEGORY_URLS.get(cat)
            if not url:
                continue
            try:
                soup = self._fetch(url)
                items = self._parse_bsr_page(soup, f"bsr_{cat.lower().replace(' ', '_')}")
                products.extend(items)
                log.info(f"BSR {cat}: {len(items)} products")
                time.sleep(random.uniform(4, 9))
            except Exception as e:
                log.warning(f"Failed BSR {cat}: {e}")
        return products

    def scrape_movers_and_shakers(self) -> list[dict]:
        try:
            soup = self._fetch(MOVERS_URL)
            return self._parse_bsr_page(soup, "movers_shakers")
        except Exception as e:
            log.warning(f"Failed Movers & Shakers: {e}")
            return []

    def scrape_new_releases(self) -> list[dict]:
        try:
            soup = self._fetch(NEW_RELEASES_URL)
            return self._parse_bsr_page(soup, "new_releases")
        except Exception as e:
            log.warning(f"Failed New Releases: {e}")
            return []

    def scrape_search_results(self, keyword: str, pages: int = 1) -> list[dict]:
        """Get Top 10 search results for competitor analysis."""
        products = []
        for page in range(1, pages + 1):
            url = f"https://www.amazon.com/s?k={keyword.replace(' ', '+')}&page={page}"
            try:
                soup = self._fetch(url)
                items = soup.select("[data-asin][data-component-type='s-search-result']")
                for item in items[:10]:
                    asin = item.get("data-asin", "")
                    title_el = item.select_one("h2 .a-link-normal span")
                    title = title_el.get_text(strip=True) if title_el else ""
                    price_el = item.select_one(".a-price .a-offscreen")
                    price = self._parse_price(price_el.get_text() if price_el else "") or 0.0
                    rating_el = item.select_one(".a-icon-alt")
                    rating = self._parse_rating(rating_el.get_text() if rating_el else "") or 0.0
                    review_el = item.select_one(".a-size-base.s-underline-text")
                    review_count = self._parse_review_count(review_el.get_text() if review_el else "") or 0
                    brand_el = item.select_one(".a-size-base-plus.a-color-base")
                    brand = brand_el.get_text(strip=True) if brand_el else "Unknown"
                    sponsored = bool(item.select_one(".s-label-popover-default"))

                    if asin:
                        products.append({
                            "asin": asin,
                            "title": title,
                            "brand": brand,
                            "price": price,
                            "rating": rating,
                            "review_count": review_count,
                            "is_sponsored": sponsored,
                            "keyword": keyword,
                            "search_rank": len(products) + 1,
                        })
                time.sleep(random.uniform(3, 7))
            except Exception as e:
                log.warning(f"Failed search for '{keyword}' p{page}: {e}")
        return products

    def scrape_reviews(self, asin: str, max_reviews: int = 50) -> list[dict]:
        """Scrape recent critical reviews for pain point analysis."""
        reviews = []
        url = f"https://www.amazon.com/product-reviews/{asin}?sortBy=recent&filterByStar=critical"
        try:
            soup = self._fetch(url)
            review_els = soup.select("[data-hook='review']")
            for rev in review_els[:max_reviews]:
                rating_el = rev.select_one("[data-hook='review-star-rating'] .a-icon-alt")
                body_el = rev.select_one("[data-hook='review-body'] span")
                title_el = rev.select_one("[data-hook='review-title'] span:not(.a-icon-alt)")
                reviews.append({
                    "rating": self._parse_rating(rating_el.get_text() if rating_el else "") or 0,
                    "title": title_el.get_text(strip=True) if title_el else "",
                    "body": body_el.get_text(strip=True) if body_el else "",
                })
        except Exception as e:
            log.warning(f"Failed reviews for {asin}: {e}")
        return reviews

    def apply_hard_filters(self, products: list[dict], exclusions: dict) -> list[dict]:
        """Remove products that violate hard exclusion rules."""
        filtered = []
        for p in products:
            title = (p.get("title") or "").lower()
            category = (p.get("bsr_category") or "").lower()

            # Check excluded categories
            excluded = False
            for exc in exclusions["excluded_categories"]:
                if exc.lower() in title or exc.lower() in category:
                    excluded = True
                    break

            # Check excluded keywords in title
            for kw in exclusions["excluded_keywords_in_title"]:
                if kw.lower() in title:
                    excluded = True
                    break

            # Price check: if price > $70, likely over budget for small seller
            if p.get("price", 0) > 70:
                excluded = True

            # Zero-price: don't exclude, flag for enrichment to fill in
            # (price will be verified during product detail page fetch)

            if not excluded:
                filtered.append(p)

        return filtered

    def enrich_product(self, product: dict) -> dict:
        """Fetch search result competitors and reviews for a product."""
        keyword = self._build_keyword(product.get("title", ""))
        if not keyword:
            return product

        # Get Top 10 search competitors
        competitors = self.scrape_search_results(keyword)
        product["competitors_top10"] = competitors
        product["keyword"] = keyword

        # Get reviews for this product
        if product.get("asin"):
            time.sleep(random.uniform(2, 5))
            reviews = self.scrape_reviews(product["asin"],
                                          max_reviews=self.config["scraping"]["reviews_per_product"])
            product["reviews_sample"] = reviews

        return product

    def _build_keyword(self, title: str) -> str:
        """Extract the most relevant 3-5 word keyword from a product title."""
        # Remove special characters and common filler words
        stop_words = {"for", "with", "and", "the", "a", "an", "of", "to", "in",
                      "pack", "set", "pcs", "piece", "pieces", "count", "black", "white"}
        words = re.findall(r'[a-zA-Z]+', title)
        filtered = [w.lower() for w in words if w.lower() not in stop_words and len(w) > 2]
        return " ".join(filtered[:4])
