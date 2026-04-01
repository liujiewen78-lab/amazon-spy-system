"""
Review Analyzer — Extract pain points and praises from Amazon reviews.
Uses OpenAI if API key available, otherwise falls back to keyword extraction.
"""

import os
import re
import json
import logging
from collections import Counter

log = logging.getLogger(__name__)

# High-signal pain point keywords
PAIN_POINT_PATTERNS = {
    "quality": ["broke", "broken", "cheap", "flimsy", "poor quality", "fell apart",
                 "stopped working", "defective", "garbage", "waste"],
    "size": ["too small", "too big", "wrong size", "doesn't fit", "not fit",
              "size issue", "smaller than", "bigger than"],
    "packaging": ["damaged", "arrived broken", "poor packaging", "not protected"],
    "description": ["not as described", "misleading", "fake", "counterfeit",
                    "different from", "misrepresented"],
    "smell": ["smell", "odor", "stink", "chemical"],
    "safety": ["dangerous", "unsafe", "sharp", "hurt", "injury"],
    "usability": ["hard to use", "difficult", "confusing", "doesn't work",
                  "not work", "useless", "complicated"],
    "logistics": ["late", "never arrived", "lost", "wrong item", "missing"],
}

PRAISE_PATTERNS = {
    "value": ["great value", "worth it", "affordable", "cheap for", "good price"],
    "quality": ["great quality", "well made", "sturdy", "durable", "solid"],
    "size": ["perfect size", "fits perfectly", "exactly right"],
    "design": ["looks great", "beautiful", "nice design", "stylish", "cute"],
    "functionality": ["works great", "works perfectly", "does the job", "as expected"],
    "packaging": ["well packaged", "nice packaging", "gift ready"],
}


class ReviewAnalyzer:
    def __init__(self, use_ai: bool = True):
        self.use_ai = use_ai and bool(os.environ.get("OPENAI_API_KEY"))
        if self.use_ai:
            try:
                from openai import OpenAI
                self.openai = OpenAI()
                log.info("ReviewAnalyzer: Using AI mode (OpenAI)")
            except ImportError:
                self.use_ai = False
                log.warning("ReviewAnalyzer: openai not installed, using keyword mode")
        else:
            log.info("ReviewAnalyzer: Using keyword extraction mode")

    def analyze_reviews(self, reviews: list[dict]) -> dict:
        """Extract structured insights from a list of reviews."""
        if not reviews:
            return {"pain_points": [], "praises": [], "improvable": False, "summary": "No reviews available"}

        if self.use_ai:
            return self._analyze_with_ai(reviews)
        else:
            return self._analyze_with_keywords(reviews)

    def _analyze_with_keywords(self, reviews: list[dict]) -> dict:
        all_text = " ".join([
            (r.get("title", "") + " " + r.get("body", "")).lower()
            for r in reviews
        ])

        pain_points = []
        for category, patterns in PAIN_POINT_PATTERNS.items():
            count = sum(1 for p in patterns if p in all_text)
            if count > 0:
                pain_points.append({
                    "category": category,
                    "signal_count": count,
                    "examples": [p for p in patterns if p in all_text][:3]
                })

        praises = []
        for category, patterns in PRAISE_PATTERNS.items():
            count = sum(1 for p in patterns if p in all_text)
            if count > 0:
                praises.append({
                    "category": category,
                    "signal_count": count,
                })

        # Sort by signal strength
        pain_points.sort(key=lambda x: x["signal_count"], reverse=True)
        praises.sort(key=lambda x: x["signal_count"], reverse=True)

        improvable = len(pain_points) >= 2 and pain_points[0]["signal_count"] >= 3

        return {
            "pain_points": pain_points[:5],
            "praises": praises[:3],
            "improvable": improvable,
            "total_reviews_analyzed": len(reviews),
            "summary": f"Top pain: {pain_points[0]['category'] if pain_points else 'none'}"
        }

    def _analyze_with_ai(self, reviews: list[dict]) -> dict:
        """Use OpenAI to extract structured insights."""
        review_text = "\n".join([
            f"[{r.get('rating', '?')}★] {r.get('title', '')} — {r.get('body', '')[:200]}"
            for r in reviews[:30]  # Limit to 30 reviews to control token cost
        ])

        prompt = f"""Analyze these Amazon product reviews and extract:
1. Top 3-5 pain points (things customers complain about)
2. Top 3 praises (things customers love)
3. Is this product improvable? (true/false — true if there are clear, fixable issues)
4. One-sentence summary

Reviews:
{review_text}

Respond in JSON format:
{{
  "pain_points": [{{"category": "...", "description": "...", "frequency": "high/medium/low"}}],
  "praises": [{{"category": "...", "description": "..."}}],
  "improvable": true/false,
  "summary": "..."
}}"""

        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            result = json.loads(response.choices[0].message.content)
            result["total_reviews_analyzed"] = len(reviews)
            return result
        except Exception as e:
            log.warning(f"AI analysis failed: {e}, falling back to keywords")
            return self._analyze_with_keywords(reviews)
