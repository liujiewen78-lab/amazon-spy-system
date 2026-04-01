"""
四个门过滤器 — 市场集中度、进入门槛、关键词切入口、评论痛点
Three-tier output: blue_ocean / red_ocean_beatable / red_ocean_avoid
"""

import logging
from typing import Literal

log = logging.getLogger(__name__)

Tier = Literal["blue_ocean", "red_ocean_beatable", "red_ocean_avoid"]


def analyze_market_concentration(competitors: list[dict], threshold: float = 0.75) -> dict:
    """
    门1: 市场集中度
    If top brand controls >75% of estimated sales in Top10 → FAIL
    """
    if not competitors:
        return {"passed": True, "top_brand_share": 0.0, "detail": "No competitor data"}

    # Estimate sales by review count * rating as proxy
    brand_scores = {}
    total_score = 0
    for c in competitors[:10]:
        brand = c.get("brand", "Unknown")
        score = (c.get("review_count") or 0) * (c.get("rating") or 3.0)
        brand_scores[brand] = brand_scores.get(brand, 0) + score
        total_score += score

    if total_score == 0:
        return {"passed": True, "top_brand_share": 0.0, "detail": "Cannot calculate"}

    top_brand = max(brand_scores, key=brand_scores.get)
    top_share = brand_scores[top_brand] / total_score

    passed = top_share <= threshold
    return {
        "passed": passed,
        "top_brand": top_brand,
        "top_brand_share": round(top_share, 3),
        "threshold": threshold,
        "detail": f"{top_brand} controls ~{top_share:.0%} of estimated sales",
        "warning": not passed
    }


def analyze_entry_barrier(competitors: list[dict],
                           high_review_threshold: int = 500,
                           new_listing_days: int = 90) -> dict:
    """
    门2: 进入门槛
    Check if any new listings (<90 days old, <500 reviews) appear in Top10.
    """
    if not competitors:
        return {"passed": True, "new_listings_count": 0, "detail": "No competitor data"}

    top10 = competitors[:10]
    low_review_count = sum(1 for c in top10 if (c.get("review_count") or 0) < high_review_threshold)
    # Note: age data requires additional scraping; approximated by review count
    # Products with <200 reviews in top10 suggest the market is penetrable

    very_low_review_count = sum(1 for c in top10 if (c.get("review_count") or 0) < 200)

    passed = low_review_count >= 2 or very_low_review_count >= 1
    return {
        "passed": passed,
        "top10_count": len(top10),
        "low_review_listings": low_review_count,
        "very_low_review_listings": very_low_review_count,
        "detail": f"{low_review_count}/10 competitors have <{high_review_threshold} reviews",
        "warning": not passed
    }


def analyze_keyword_opportunity(keyword: str, competitors: list[dict]) -> dict:
    """
    门3: 关键词切入口
    Check for low-competition long-tail keyword opportunities.
    (Full implementation requires Helium10 or similar; here we use competitor density as proxy)
    """
    if not competitors:
        return {"passed": True, "opportunity_keywords": [], "detail": "No data"}

    # Proxy: if avg competitor review count < 1000, there's likely keyword room
    avg_reviews = sum(c.get("review_count") or 0 for c in competitors[:10]) / max(len(competitors[:10]), 1)
    has_sponsored_only = all(c.get("is_sponsored", False) for c in competitors[:5])

    # Low avg reviews suggest accessible market
    passed = avg_reviews < 1000 and not has_sponsored_only

    # Generate long-tail keyword suggestions
    base_words = keyword.split()
    long_tails = [
        f"{keyword} for women",
        f"{keyword} gift",
        f"best {keyword}",
        f"{keyword} small",
        f"mini {keyword}",
    ] if len(base_words) <= 3 else []

    return {
        "passed": passed,
        "avg_competitor_reviews": round(avg_reviews),
        "opportunity_keywords": long_tails,
        "detail": f"Avg competitor reviews: {avg_reviews:.0f}",
        "warning": not passed
    }


def analyze_review_pain_points(review_analysis: dict) -> dict:
    """
    门4: 评论痛点可改造性
    Check if there are clear, fixable pain points in competitor reviews.
    """
    if not review_analysis:
        return {"passed": False, "detail": "No review analysis available"}

    improvable = review_analysis.get("improvable", False)
    pain_points = review_analysis.get("pain_points", [])
    top_pain = pain_points[0] if pain_points else None

    return {
        "passed": improvable,
        "improvable": improvable,
        "top_pain_point": top_pain.get("category") if top_pain else None,
        "pain_point_count": len(pain_points),
        "detail": review_analysis.get("summary", ""),
        "warning": not improvable
    }


def determine_tier(gate1: dict, gate2: dict, gate3: dict, gate4: dict) -> Tier:
    """
    三层结果判断:
    - red_ocean_avoid: 门1失败（品牌垄断）或 门2+门3 同时失败
    - blue_ocean: 四个门全过
    - red_ocean_beatable: 中间情况
    """
    # Hard fail conditions
    if not gate1["passed"]:
        return "red_ocean_avoid"
    if not gate2["passed"] and not gate3["passed"]:
        return "red_ocean_avoid"

    # All gates passed
    if gate1["passed"] and gate2["passed"] and gate3["passed"] and gate4["passed"]:
        return "blue_ocean"

    # Some warnings but not fatal
    return "red_ocean_beatable"


def run_all_gates(product: dict, review_analysis: dict, config: dict) -> dict:
    """Run all four gates and return combined result."""
    competitors = product.get("competitors_top10", [])
    keyword = product.get("keyword", product.get("title", "")[:30])

    mc = config["market_concentration"]
    eb = config["entry_barrier"]

    gate1 = analyze_market_concentration(competitors, mc["red_threshold"])
    gate2 = analyze_entry_barrier(competitors, eb["high_review_threshold"], eb["new_listing_days"])
    gate3 = analyze_keyword_opportunity(keyword, competitors)
    gate4 = analyze_review_pain_points(review_analysis)

    tier = determine_tier(gate1, gate2, gate3, gate4)

    return {
        "tier": tier,
        "gates": {
            "market_concentration": gate1,
            "entry_barrier": gate2,
            "keyword_opportunity": gate3,
            "review_pain_points": gate4,
        },
        "gates_passed": sum([gate1["passed"], gate2["passed"], gate3["passed"], gate4["passed"]]),
    }
